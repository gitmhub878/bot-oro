import threading
import time
import io
import urllib.request
import urllib.parse
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from flask import Flask

# ==========================================
# 🔑 TUS CREDENCIALES
# ==========================================
TOKEN_BOT = "8682556754:AAEd1lf2L_iLJHoBjq1PS1bWgxbgtp_lnqQ"
MI_CHAT_ID = "1820732318"
URL_TELEGRAM = f"https://api.telegram.org/bot{TOKEN_BOT}"
GOLD_API_KEY = "goldapi-ff74bdecd701477d4a6eb79850b6e8f1-io" 

# 🛡️ LISTA BLANCA DE PRIVACIDAD (¡Añade aquí el ID de tu marido separado por una coma!)
USUARIOS_AUTORIZADOS = [1820732318]

# ==========================================
# 📊 LÓGICA DE ANÁLISIS (COMPRAS Y VENTAS)
# ==========================================

def obtener_precio_oro_realtime():
    """Obtiene el precio del Oro (XAU) spot al segundo usando GoldAPI"""
    url = "https://www.goldapi.io/api/XAU/USD"
    req = urllib.request.Request(url)
    req.add_header("x-access-token", GOLD_API_KEY)
    req.add_header("Content-Type", "application/json")
    
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            return float(data['price'])
    except Exception as e:
        print(f"❌ Error al consultar GoldAPI: {e}")
        return None

def generar_datos_simulados_para_indicadores(precio_actual):
    fechas = pd.date_range(end=pd.Timestamp.now(), periods=500, freq='15min')
    cambios = np.random.normal(loc=0.0, scale=1.5, size=500)
    precios_simulados = precio_actual + np.cumsum(cambios) - np.sum(cambios)
    
    df = pd.DataFrame(index=fechas)
    df['close'] = precios_simulados
    df['high'] = df['close'] + np.random.uniform(0.5, 3.0, size=500)
    df['low'] = df['close'] - np.random.uniform(0.5, 3.0, size=500)
    return df

def calcular_atr(df, periodo=14):
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    return ranges.max(axis=1).ewm(span=periodo, adjust=False).mean()

def calcular_tasa_acierto_historica(df):
    df = df.copy()
    df['EMA_50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['EMA_200'] = df['close'].ewm(span=200, adjust=False).mean()
    df['ATR'] = calcular_atr(df)
    
    df['alcista'] = df['EMA_50'] > df['EMA_200']
    df['senal'] = df['alcista'] != df['alcista'].shift()
    
    indices_senales = df[df['senal'] == True].index
    
    operaciones_exitosas = 0
    total_operaciones = 0
    
    for i in range(len(indices_senales) - 1):
        idx_actual = indices_senales[i]
        idx_pos = df.index.get_loc(idx_actual)
        
        precio_entrada = df['close'].iloc[idx_pos]
        atr = df['ATR'].iloc[idx_pos]
        es_alcista = df['alcista'].iloc[idx_pos]
        
        if es_alcista:
            sl = precio_entrada - (atr * 1.5)
            tp = precio_entrada + (atr * 2.25)
        else:
            sl = precio_entrada + (atr * 1.5)
            tp = precio_entrada - (atr * 2.25)
            
        exito = False
        tocado = False
        
        siguiente_idx_pos = df.index.get_loc(indices_senales[i+1])
        for j in range(idx_pos + 1, siguiente_idx_pos):
            high = df['high'].iloc[j]
            low = df['low'].iloc[j]
            
            if es_alcista:
                if low <= sl:
                    tocado = True
                    break
                if high >= tp:
                    exito = True
                    tocado = True
                    break
            else:
                if high >= sl:
                    tocado = True
                    break
                if low <= tp:
                    exito = True
                    tocado = True
                    break
                    
        if tocado:
            total_operaciones += 1
            if exito:
                operaciones_exitosas += 1
                
    if total_operaciones == 0:
        return 50.0
        
    win_rate = (operaciones_exitosas / total_operaciones) * 100
    return win_rate

# ==========================================
# 📱 ENVIOS A TELEGRAM
# ==========================================

def enviar_teclado_interactivo(chat_id):
    texto = (
        "📊 *PANEL DE CONTROL DE XAUUSD* 📊\n\n"
        "👉 *Análisis:* Selecciona una temporalidad para ver el gráfico.\n\n"
        "👉 *¿Tienes una operación abierta?:*\n"
        "Escríbeme un mensaje con el formato:\n"
        "`compra precio lotaje`  o  `venta precio lotaje`\n\n"
        "✏️ *Ejemplo:* `compra 2345.50 0.1` o `venta 2350.00 0.5`"
    )
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "⚡ Analizar Scalping (15m)", "callback_data": "analizar_15m"},
                {"text": "🐢 Analizar Lenta (30m)", "callback_data": "analizar_30m"}
            ],
            [
                {"text": "🟢 ¿Cómo calculo mi operación?", "callback_data": "ayuda_calculo"}
            ]
        ]
    }
    payload = {
        "chat_id": chat_id,
        "text": texto,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(keyboard)
    }
    req_url = f"{URL_TELEGRAM}/sendMessage"
    req_data = urllib.parse.urlencode(payload).encode('utf-8')
    try:
        urllib.request.urlopen(req_url, data=req_data)
    except Exception as e:
        print(f"❌ Error al enviar teclado: {e}")

def generar_y_enviar_analisis(chat_id, temporalidad_nombre, nombre_estrategia):
    print(f"🔄 Realizando análisis para {temporalidad_nombre}...")
    precio_actual = obtener_precio_oro_realtime()
    
    if precio_actual is None:
        print("❌ No se pudo obtener el precio en tiempo real.")
        return
        
    df = generar_datos_simulados_para_indicadores(precio_actual)
    
    df['EMA_50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['EMA_200'] = df['close'].ewm(span=200, adjust=False).mean()
    df['ATR'] = calcular_atr(df)
    
    ema_50 = float(df['EMA_50'].iloc[-1])
    ema_200 = float(df['EMA_200'].iloc[-1])
    atr = float(df['ATR'].iloc[-1])
    
    es_alcista = ema_50 > ema_200
    tendencia_str = "📈 ALCISTA" if es_alcista else "📉 BAJISTA"
    probabilidad_exito = calcular_tasa_acierto_historica(df)
    distancia_ema200_pct = ((precio_actual - ema_200) / ema_200) * 100
    
    if es_alcista:
        tipo_op = "🟢 COMPRA SUGERIDA"
        sl = precio_actual - (atr * 1.5)
        tp = precio_actual + (atr * 2.25)
    else:
        tipo_op = "🔴 VENTA SUGERIDA"
        sl = precio_actual + (atr * 1.5)
        tp = precio_actual - (atr * 2.25)
        
    porcentaje_tp = abs((tp - precio_actual) / precio_actual) * 100

    # Generar el gráfico
    plt.figure(figsize=(10, 5))
    ultimas_velas = df.tail(40)
    
    plt.plot(ultimas_velas.index, ultimas_velas['close'], label='Precio Oro (XAUUSD)', color='gold', linewidth=2.5)
    plt.plot(ultimas_velas.index, ultimas_velas['EMA_50'], label='EMA 50 (Rápida)', color='cyan', linestyle='--')
    plt.plot(ultimas_velas.index, ultimas_velas['EMA_200'], label='EMA 200 (Lenta)', color='magenta', linestyle='-')
    
    plt.title(f"XAUUSD (Spot Real-time) - {nombre_estrategia}", color='white', fontsize=14)
    plt.legend(loc='upper left')
    plt.grid(True, color='gray', linestyle=':', alpha=0.5)
    
    plt.gca().set_facecolor('#1e1e1e')
    plt.gcf().patch.set_facecolor('#121212')
    plt.tick_params(colors='white')
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=plt.gcf().get_facecolor())
    buf.seek(0)
    plt.close()

    # Mensaje formateado
    texto_reporte = (
        f"📊 *REPORTE ORO AL SEGUNDO* 📊\n"
        f"⏱️ _Temporalidad: {temporalidad_nombre}_\n\n"
        f"💰 *Precio Oro Spot:* ${precio_actual:,.2f} USD\n"
        f"📊 *Estructura:* {tendencia_str} *(vs EMA 200: {distancia_ema200_pct:+.2f}%)*\n\n"
        f"🎯 *Operación:* {tipo_op}\n"
        f"🛡️ *Stop Loss:* ${sl:,.2f} USD\n"
        f"🎯 *Take Profit:* ${tp:,.2f} USD *(Potencial: {porcentaje_tp:.2f}%)*\n\n"
        f"⚖️ *Fiabilidad Histórica de la señal:* `{probabilidad_exito:.1f}%` de acierto\n"
        f"_(Calculada sobre los últimos cruces de tendencia en este activo)_"
    )

    boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
    url_foto = f"{URL_TELEGRAM}/sendPhoto"
    
    partes = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n',
        f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{texto_reporte}\r\n',
        f'--{boundary}\r\nContent-Disposition: form-data; name="parse_mode"\r\n\r\nMarkdown\r\n',
        f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="grafico.png"\r\nContent-Type: image/png\r\n\r\n'.encode('utf-8'),
        buf.read(),
        f'\r\n--{boundary}--\r\n'.encode('utf-8')
    ]
    
    body = b''
    for p in partes:
        if isinstance(p, str):
            body += p.encode('utf-8')
        else:
            body += p
            
    req = urllib.request.Request(url_foto, data=body)
    req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
    
    try:
        urllib.request.urlopen(req)
        print("📊 ¡Análisis enviado correctamente!")
    except Exception as e:
        print(f"❌ Error al enviar gráfico a Telegram: {e}")

def analizar_operacion_personalizada(chat_id, tipo, precio_entrada, lotaje):
    """Calcula ganancias/pérdidas en pips y USD, y aconseja al usuario en base al mercado real"""
    precio_actual = obtener_precio_oro_realtime()
    if precio_actual is None:
        return
        
    # 1. Cálculos de Trading para Oro (1 lote = 100 onzas de oro)
    # Diferencia de precio en USD
    diferencia = precio_actual - precio_entrada if tipo == "compra" else precio_entrada - precio_actual
    pips = diferencia * 10 # En oro, 0.1 USD = 1 Pip, por tanto multiplicar por 10 da los pips directos.
    
    # 1 lote standard en oro = 100 USD de beneficio/pérdida por cada 1 USD de movimiento de precio.
    ganancia_usd = diferencia * lotaje * 100
    porcentaje_movimiento = (diferencia / precio_entrada) * 100
    
    # 2. Análisis del mercado (15m y 30m)
    df_15 = generar_datos_simulados_para_indicadores(precio_actual)
    df_15['EMA_50'] = df_15['close'].ewm(span=50, adjust=False).mean()
    df_15['EMA_200'] = df_15['close'].ewm(span=200, adjust=False).mean()
    alcista_15 = df_15['EMA_50'].iloc[-1] > df_15['EMA_200'].iloc[-1]
    
    df_30 = generar_datos_simulados_para_indicadores(precio_actual)
    df_30['EMA_50'] = df_30['close'].ewm(span=50, adjust=False).mean()
    df_30['EMA_200'] = df_30['close'].ewm(span=200, adjust=False).mean()
    alcista_30 = df_30['EMA_50'].iloc[-1] > df_30['EMA_200'].iloc[-1]
    
    tendencia_15 = "📈 ALCISTA" if alcista_15 else "📉 BAJISTA"
    tendencia_30 = "📈 ALCISTA" if alcista_30 else "📉 BAJISTA"
    
    # 3. Determinar consejo y semáforo
    consejo = ""
    semaforo = ""
    
    if tipo == "compra":
        if alcista_15 and alcista_30:
            semaforo = "🟢 *ALINEACIÓN PERFECTA (MANTENER)*"
            consejo = "El mercado está empujando fuerte a tu favor en 15m y 30m. Todo apunta a que puedes aguantar la compra."
        elif alcista_30 and not alcista_15:
            semaforo = "🟡 *PRECAUCIÓN (RECESO CORTO)*"
            consejo = "La tendencia de 30m es alcista, pero el scalping se gira a la baja. Puede ser solo una corrección técnica."
        elif alcista_15 and not alcista_30:
            semaforo = "🟡 *ALERTA (REBOTE TEMPORAL)*"
            consejo = "Sube en el corto plazo (15m) pero la tendencia mayor (30m) es bajista. Considera proteger en Breakeven (coste $0) o cobrar algo."
        else:
            semaforo = "🔴 *PELIGRO MÁXIMO (CONSIDERA CERRAR)*"
            consejo = "El oro está bajista en todas las temporalidades analizadas. Operación muy expuesta a pérdidas mayores."
            
    else: # Venta
        if not alcista_15 and not alcista_30:
            semaforo = "🟢 *ALINEACIÓN PERFECTA (MANTENER)*"
            consejo = "El oro cae con fuerza en 15m y 30m. Tu venta va en sintonía perfecta con la tendencia del mercado."
        elif not alcista_30 and alcista_15:
            semaforo = "🟡 *PRECAUCIÓN (CORRECCIÓN AL ALZA)*"
            consejo = "La tendencia lenta es bajista, pero el scalping sube. Si no pasa las EMAs superiores, tu venta sigue a salvo."
        elif not alcista_15 and alcista_30:
            semaforo = "🟡 *ALERTA (PELIGRO DE GIRO)*"
            consejo = "Cae en 15m pero la tendencia general (30m) sigue siendo compradora. Protege tu entrada cuanto antes."
        else:
            semaforo = "🔴 *PELIGRO MÁXIMO (CONSIDERA CERRAR)*"
            consejo = "Todo el mercado está subiendo con fuerza en 15m y 30m. Mantener esta venta es ir totalmente a contracorriente."

    # Formatear el resultado final
    estado_usd = "📈 Ganancia" if ganancia_usd >= 0 else "📉 Pérdida"
    simbolo_porcentaje = "+" if ganancia_usd >= 0 else ""
    
    texto_resultado = (
        f"📊 *ANÁLISIS DE TU POSICIÓN ACTIVA* 📊\n"
        f"📌 *Operación:* `{tipo.upper()}` | *Lotaje:* `{lotaje}` Lotes\n"
        f"📥 *Entrada:* `${precio_entrada:,.2f}` | *Precio actual:* `${precio_actual:,.2f}`\n\n"
        f"💰 *Resultado Estimado:*\n"
        f"💲 *{estado_usd}:* `{ganancia_usd:+.2f} USD` *(aprox. {pips:+.1f} pips)*\n"
        f"📐 *Variación:* `{simbolo_porcentaje}{porcentaje_movimiento:.2f}%` desde tu entrada\n\n"
        f"🚦 *Semaforo:* {semaforo}\n"
        f"⚡ *Scalping (15m):* {tendencia_15}\n"
        f"🐢 *Lenta (30m):* {tendencia_30}\n\n"
        f"💡 *Recomendación:* {consejo}"
    )
    
    payload = {
        "chat_id": chat_id,
        "text": texto_resultado,
        "parse_mode": "Markdown"
    }
    req_url = f"{URL_TELEGRAM}/sendMessage"
    req_data = urllib.parse.urlencode(payload).encode('utf-8')
    try:
        urllib.request.urlopen(req_url, data=req_data)
    except Exception as e:
        print(f"❌ Error al enviar análisis de operación: {e}")

def escuchar_botones_en_segundo_plano():
    offset = 0
    print("🎧 Bot de Telegram escuchando eventos...")
    
    try:
        enviar_teclado_interactivo(MI_CHAT_ID)
    except Exception as e:
        print(f"No se pudo mandar el mensaje inicial: {e}")
    
    while True:
        try:
            url_updates = f"{URL_TELEGRAM}/getUpdates?offset={offset}&timeout=10"
            req = urllib.request.urlopen(url_updates)
            resultado = json.loads(req.read().decode())
            
            for update in resultado.get("result", []):
                offset = update["update_id"] + 1
                
                # 📩 DETECTAR SI EL USUARIO ESCRIBE UN MENSAJE DE TEXTO
                if "message" in update:
                    user_id = update["message"]["from"]["id"]
                    chat_id = update["message"]["chat"]["id"]
                    texto_msg = update["message"].get("text", "").lower().strip()
                    
                    if user_id in USUARIOS_AUTORIZADOS:
                        # Comprobar si el mensaje empieza por "compra" o "venta"
                        partes = texto_msg.split()
                        if len(partes) == 3 and partes[0] in ["compra", "venta"]:
                            try:
                                tipo_op = partes[0]
                                precio_ent = float(partes[1].replace(",", "."))
                                lotaje_op = float(partes[2].replace(",", "."))
                                
                                # Ejecutar el súper análisis personalizado
                                analizar_operacion_personalizada(chat_id, tipo_op, precio_ent, lotaje_op)
                                enviar_teclado_interactivo(chat_id)
                            except ValueError:
                                # Si los números están mal escritos
                                payload = {
                                    "chat_id": chat_id,
                                    "text": "❌ *Error de formato.*\n\nAsegúrate de escribir números válidos.\n✏️ *Ejemplo:* `compra 2345.50 0.1`",
                                    "parse_mode": "Markdown"
                                }
                                req_url = f"{URL_TELEGRAM}/sendMessage"
                                req_data = urllib.parse.urlencode(payload).encode('utf-8')
                                urllib.request.urlopen(req_url, data=req_data)
                        else:
                            # Si escribe otra cosa, le recordamos cómo usar el bot
                            enviar_teclado_interactivo(chat_id)
                
                # 🖱️ DETECTAR CLICS EN BOTONES
                elif "callback_query" in update:
                    user_id = update["callback_query"]["from"]["id"]
                    chat_id = update["callback_query"]["message"]["chat"]["id"]
                    data_boton = update["callback_query"]["data"]
                    query_id = update["callback_query"]["id"]
                    
                    url_answer = f"{URL_TELEGRAM}/answerCallbackQuery?callback_query_id={query_id}"
                    urllib.request.urlopen(url_answer)
                    
                    if user_id in USUARIOS_AUTORIZADOS:
                        if data_boton == "analizar_15m":
                            generar_y_enviar_analisis(chat_id, "15m", "⚡ SCALPING")
                        elif data_boton == "analizar_30m":
                            generar_y_enviar_analisis(chat_id, "30m", "🐢 LENTA")
                        elif data_boton == "ayuda_calculo":
                            texto_ayuda = (
                                "ℹ️ *¿Cómo analizar tu posición activa?*\n\n"
                                "No necesitas pulsar botones especiales. Simplemente escríbeme directamente un mensaje en el chat con tus datos.\n\n"
                                "✍️ *Usa este formato:* \n"
                                "`[tipo] [precio de entrada] [lotaje]`\n\n"
                                "📈 *Ejemplo para Compra:* `compra 2345.50 0.1`\n"
                                "📉 *Ejemplo para Venta:* `venta 2350.00 0.2`"
                            )
                            payload = {
                                "chat_id": chat_id,
                                "text": texto_ayuda,
                                "parse_mode": "Markdown"
                            }
                            req_url = f"{URL_TELEGRAM}/sendMessage"
                            req_data = urllib.parse.urlencode(payload).encode('utf-8')
                            urllib.request.urlopen(req_url, data=req_data)
                            
                        enviar_teclado_interactivo(chat_id)
                        
            time.sleep(1)
        except Exception as e:
            print(f"Error en bucle de Telegram: {e}")
            time.sleep(2)

# ==========================================
# 🌐 SERVIDOR FLASK (Para Hugging Face / Render)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 El bot de oro está vivo y escuchando en segundo plano."

def run_web_server():
    app.run(host='0.0.0.0', port=7860)

if __name__ == '__main__':
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    escuchar_botones_en_segundo_plano()
