import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from sklearn.linear_model import LogisticRegression

# Cadena de conexión a PostgreSQL con SQLAlchemy
DATABASE_URL = "postgresql://dbsecurity_user:27PdSd9U8rvelKWnSmhR0MrN20M1uAsq@dpg-cuv3f2a3esus73bl48d0-a.oregon-postgres.render.com/dbsecurity?sslmode=require"

# Crear un motor de conexión con SQLAlchemy
engine = create_engine(DATABASE_URL)

# Obtener los datos de la base de datos
def obtener_datos():
    query = """
            SELECT fecha AT TIME ZONE 'UTC' AT TIME ZONE 'America/Lima' AS fecha_local, estado 
            FROM hechos
        """
    df = pd.read_sql(query, engine)  # Usamos el motor de SQLAlchemy para la conexión
    # Convertir la columna 'fecha' a datetime
    df['fecha_hora'] = pd.to_datetime(df['fecha_local'], errors='coerce')

    # Filtrar los accesos permitidos
    df['permitidos'] = (df['estado'] == 'Acceso permitido').astype(int)

    # Extraer la hora de la fecha
    df['hora'] = df['fecha_hora'].dt.hour

    return df

# Función para entrenar el modelo de regresión logística
def entrenar_modelo():
    df = obtener_datos()

    # Crear las variables X e y para el modelo de regresión
    X = df[['hora']]  # Hora del día
    y = df['permitidos']  # Número de accesos permitidos (0 o 1)

    # Entrenar el modelo de regresión logística
    modelo = LogisticRegression()
    modelo.fit(X, y)

    return modelo

# Modelo entrenado (guardamos el modelo para evitar entrenarlo cada vez que se hace una predicción)
modelo = entrenar_modelo()

# Función para predecir accesos según la hora
def predecir_acceso(hora):
    try:
        # Realizar la predicción para la hora solicitada
        probabilidad = modelo.predict_proba(np.array([[hora]]))  # Predicción de la probabilidad
        prediccion = probabilidad[0][1]  # Obtener la probabilidad de que el acceso sea permitido
        return prediccion  # Retornar la probabilidad entre 0 y 1
    
    except Exception as e:
        return str(e)
