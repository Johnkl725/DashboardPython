from flask import Flask, jsonify, render_template, request
from sqlalchemy import create_engine
import pandas as pd
from models.prediccion_model import predecir_acceso
from statsmodels.tsa.seasonal import STL  # Asegúrate de importar STL
import os
app = Flask(__name__)

# Cadena de conexión a PostgreSQL con SQLAlchemy
DATABASE_URL = "postgresql://dbsecurity_user:27PdSd9U8rvelKWnSmhR0MrN20M1uAsq@dpg-cuv3f2a3esus73bl48d0-a.oregon-postgres.render.com/dbsecurity?sslmode=require"

# Crear un motor de conexión con SQLAlchemy
engine = create_engine(DATABASE_URL)

# Conexión a la base de datos usando SQLAlchemy
def get_db_connection():
    return engine.connect()

# Página principal con la gráfica interactiva
@app.route("/datos_hechos")
def datos_hechos():
    return render_template("grafico.html")

# API para obtener el rango de días registrados en la base de datos
@app.route("/api/dias_registrados")
def dias_registrados():
    try:
        conn = get_db_connection()
        query = "SELECT MIN(fecha) AS primera_fecha, MAX(fecha) AS ultima_fecha FROM hechos"
        df = pd.read_sql(query, conn)
        conn.close()

        # Verificar que haya datos en la consulta
        if df.empty or df["primera_fecha"].isnull().any() or df["ultima_fecha"].isnull().any():
            return jsonify({"error": "No hay datos suficientes para calcular el rango de días."})

        # Convertir fechas a tipo datetime
        primera_fecha = pd.to_datetime(df["primera_fecha"][0])
        ultima_fecha = pd.to_datetime(df["ultima_fecha"][0])

        # Calcular la diferencia de días
        dias_transcurridos = (ultima_fecha - primera_fecha).days + 1  # +1 para incluir el primer día

        return jsonify({"dias_transcurridos": dias_transcurridos})

    except Exception as e:
        return jsonify({"error": str(e)})

# API para obtener el total de accesos permitidos y denegados
@app.route("/api/total_accesos")
def total_accesos():
    try:
        conn = get_db_connection()
        query = "SELECT estado FROM hechos"
        df = pd.read_sql(query, conn)
        conn.close()

        # Contar accesos permitidos y denegados
        total_permitidos = int((df['estado'] == 'Acceso permitido').sum())  # Convertir a int estándar
        total_denegados = int((df['estado'] == 'Acceso denegado').sum())  # Convertir a int estándar

        return jsonify({
            "total_permitidos": total_permitidos,
            "total_denegados": total_denegados
        })

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

        # Convertir 'fecha_local' a datetime
        df['fecha_hora'] = pd.to_datetime(df['fecha_local'], errors='coerce')

        # Crear columnas de permitidos y denegados
        df['permitidos'] = (df['estado'] == 'Acceso permitido').astype(int)
        df['denegados'] = (df['estado'] == 'Acceso denegado').astype(int)

        # Agrupar los datos por fecha
        df_grouped = df.groupby('fecha_hora', as_index=False)[['permitidos', 'denegados']].sum()

        # Convertir la fecha a string para facilitar el manejo
        df_grouped['fecha_hora'] = df_grouped['fecha_hora'].astype(str)

        return jsonify(df_grouped.to_dict(orient="records"))

    except Exception as e:
        return jsonify({"error": str(e)})

# API para obtener las series temporales (tendencia, estacionalidad, residuo)
@app.route("/api/series_temporales")
def series_temporales():
    try:
        # Obtener conexión y consultar la base de datos
        conn = get_db_connection()
        query = """
            SELECT fecha AT TIME ZONE 'UTC' AT TIME ZONE 'America/Lima' AS fecha_local, estado 
            FROM hechos
        """
        df = pd.read_sql(query, conn)
        conn.close()

        # Verificar si los datos están vacíos
        if df.empty:
            return jsonify({"error": "No se encontraron datos en la base de datos."})

        # Convertir 'fecha_local' a datetime
        df['fecha_hora'] = pd.to_datetime(df['fecha_local'], errors='coerce')
        df['permitidos'] = (df['estado'] == 'Acceso permitido').astype(int)

        # Agrupar por fecha y sumar los accesos permitidos
        df_grouped = df.groupby('fecha_hora', as_index=False)[['permitidos']].sum()

        # Comprobar si hay suficientes datos para realizar la descomposición STL
        if len(df_grouped) < 2:
            return jsonify({"error": "No hay suficientes datos para realizar la descomposición STL."})

        # Usamos la serie de 'permitidos' para generar los cálculos
        df_grouped = df_grouped.set_index('fecha_hora')

        # Realizar descomposición STL (estacionalidad + tendencia)
        stl = STL(df_grouped['permitidos'], period=365)
        result = stl.fit()

        # Extraer la tendencia, estacionalidad y residuo
        tendencia = result.trend.dropna()
        estacionalidad = result.seasonal.dropna()
        residuo = result.resid.dropna()

        # Crear el formato adecuado para enviar como respuesta
        response_data = {
            "tendencia": [{"fecha": str(fecha), "valor": valor} for fecha, valor in zip(tendencia.index, tendencia)],
            "estacionalidad": [{"fecha": str(fecha), "valor": valor} for fecha, valor in zip(estacionalidad.index, estacionalidad)],
            "residuo": [{"fecha": str(fecha), "valor": valor} for fecha, valor in zip(residuo.index, residuo)]
        }

        return jsonify(response_data)

    except Exception as e:
        # Registra el error en los logs de Flask y devuelve un mensaje de error adecuado
        app.logger.error(f"Error al obtener los datos de series temporales: {str(e)}")
        return jsonify({"error": "Error al obtener los datos de series temporales."})



# API para realizar la predicción de accesos
@app.route("/api/predict_acceso")
def predict_acceso_route():
    try:
        hora = request.args.get('hora', type=int)
        if hora is None or hora < 0 or hora > 23:
            return jsonify({"error": "Hora inválida. Debe estar entre 0 y 23."})

        # Realizar la predicción con regresión logística
        prediccion = predecir_acceso(hora)

        return jsonify({"prediccion": prediccion})

    except Exception as e:
        return jsonify({"error": str(e)})



if __name__ == "__main__":
    # Usa la variable de entorno 'PORT' para el puerto o 5000 por defecto
    port = int(os.environ.get("PORT", 5000))  
    app.run(host="0.0.0.0", port=port)

