from flask import Flask, jsonify, render_template, request
from sqlalchemy import create_engine
import pandas as pd
from models.prediccion_model import predecir_acceso
from statsmodels.tsa.seasonal import STL  # Asegúrate de importar STL
from flask_cors import CORS
from flask_socketio import SocketIO, emit  # Importa SocketIO y emit
import os

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app)  # Inicializa SocketIO

# Cadena de conexión a PostgreSQL con SQLAlchemy
DATABASE_URL = "postgresql://dbsecurity_user:27PdSd9U8rvelKWnSmhR0MrN20M1uAsq@dpg-cuv3f2a3esus73bl48d0-a.oregon-postgres.render.com/dbsecurity?sslmode=require"
engine = create_engine(DATABASE_URL)

# Conexión a la base de datos usando SQLAlchemy
def get_db_connection():
    return engine.connect()

@app.route("/datos_hechos")
def datos_hechos():
    return render_template("grafico.html")

@app.route("/api/dias_registrados")
def dias_registrados():
    try:
        conn = get_db_connection()
        query = "SELECT MIN(fecha) AS primera_fecha, MAX(fecha) AS ultima_fecha FROM hechos"
        df = pd.read_sql(query, conn)
        conn.close()

        if df.empty or df["primera_fecha"].isnull().any() or df["ultima_fecha"].isnull().any():
            return jsonify({"error": "No hay datos suficientes para calcular el rango de días."})

        primera_fecha = pd.to_datetime(df["primera_fecha"][0])
        ultima_fecha = pd.to_datetime(df["ultima_fecha"][0])
        dias_transcurridos = (ultima_fecha - primera_fecha).days + 1
        return jsonify({"dias_transcurridos": dias_transcurridos})

    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/api/data")
def get_data():
    try:
        conn = get_db_connection()
        query = """
            SELECT fecha AT TIME ZONE 'UTC' AT TIME ZONE 'America/Lima' AS fecha_local, estado 
            FROM hechos
        """
        df = pd.read_sql(query, conn)
        conn.close()

        if df.empty:
            return jsonify({"error": "No se encontraron datos en la base de datos."})

        df['fecha_hora'] = pd.to_datetime(df['fecha_local'], errors='coerce')
        df['permitidos'] = (df['estado'] == 'Acceso permitido').astype(int)
        df['denegados'] = (df['estado'] == 'Acceso denegado').astype(int)

        df_grouped = df.groupby('fecha_hora', as_index=False)[['permitidos', 'denegados']].sum()
        df_grouped['fecha_hora'] = df_grouped['fecha_hora'].astype(str)

        return jsonify(df_grouped.to_dict(orient="records"))

    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/api/series_temporales")
def series_temporales():
    try:
        conn = get_db_connection()
        query = """
            SELECT fecha AT TIME ZONE 'UTC' AT TIME ZONE 'America/Lima' AS fecha_local, estado 
            FROM hechos
        """
        df = pd.read_sql(query, conn)
        conn.close()

        if df.empty:
            return jsonify({"error": "No se encontraron datos en la base de datos."})

        df['fecha_hora'] = pd.to_datetime(df['fecha_local'], errors='coerce')
        df['permitidos'] = (df['estado'] == 'Acceso permitido').astype(int)

        df_grouped = df.groupby('fecha_hora', as_index=False)[['permitidos']].sum()

        if len(df_grouped) < 2:
            return jsonify({"error": "No hay suficientes datos para realizar la descomposición STL."})

        df_grouped = df_grouped.set_index('fecha_hora')
        stl = STL(df_grouped['permitidos'], period=365)
        result = stl.fit()

        tendencia = result.trend.dropna()
        estacionalidad = result.seasonal.dropna()
        residuo = result.resid.dropna()

        response_data = {
            "tendencia": [{"fecha": str(fecha), "valor": valor} for fecha, valor in zip(tendencia.index, tendencia)],
            "estacionalidad": [{"fecha": str(fecha), "valor": valor} for fecha, valor in zip(estacionalidad.index, estacionalidad)],
            "residuo": [{"fecha": str(fecha), "valor": valor} for fecha, valor in zip(residuo.index, residuo)]
        }

        return jsonify(response_data)

    except Exception as e:
        app.logger.error(f"Error al obtener los datos de series temporales: {str(e)}")
        return jsonify({"error": "Error al obtener los datos de series temporales."})

@app.route("/api/predict_acceso")
def predict_acceso_route():
    try:
        hora = request.args.get('hora', type=int)
        if hora is None or hora < 0 or hora > 23:
            return jsonify({"error": "Hora inválida. Debe estar entre 0 y 23."})

        prediccion = predecir_acceso(hora)
        return jsonify({"prediccion": prediccion})

    except Exception as e:
        return jsonify({"error": str(e)})

# Emisión de datos a través de WebSocket
def send_data():
    conn = get_db_connection()
    query = "SELECT fecha, estado FROM hechos"
    df = pd.read_sql(query, conn)
    conn.close()

    df['fecha'] = pd.to_datetime(df['fecha'])
    df_grouped = df.groupby('fecha').sum()

    socketio.emit('update_graph', df_grouped.to_dict(orient="records"))

if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=5000)  # Usa SocketIO para correr el servidor
