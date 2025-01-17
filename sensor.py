import time
import VL53L1X
import logging
from periphery import GPIO
import paho.mqtt.client as mqtt
import json
import subprocess

# Configuración de logging
logging.basicConfig(
    filename='vl53l1x_dual_mqtt.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

SHORT_RANGE_MODE = 2
RESET_PIN_1 = 6   # GPIOA6 corresponde al pin físico 12
RESET_PIN_2 = 67  # GPIOC3 corresponde al pin físico 24
I2C_ADDRESS = 0x29  # Dirección I2C predeterminada

# Configuración MQTT
MQTT_SERVER = "192.168.123.1"
MQTT_PORT = 1883
MQTT_TOPIC_1 = "sensor/meter/1"  # Asegúrate de que son diferentes
MQTT_TOPIC_2 = "sensor/meter/2"

# Configuración del cliente MQTT
def connect_mqtt():
    client = mqtt.Client()
    while True:
        try:
            client.connect(MQTT_SERVER, MQTT_PORT, 60)
            logging.info("Conexión exitosa al servidor MQTT")
            return client
        except Exception as e:
            logging.error(f"Error al conectar con MQTT: {e}")
            print(f"Error al conectar con MQTT: {e}. Reintentando en 5 segundos...")
            time.sleep(5)

client = connect_mqtt()

def setup_gpio(pin):
    gpio = GPIO(pin, "out")
    gpio.write(False)  # Asegura que el sensor esté apagado inicialmente
    return gpio

def initialize_sensor(i2c_address, i2c_bus=0):
    try:
        tof = VL53L1X.VL53L1X(i2c_bus=i2c_bus, i2c_address=i2c_address)
        tof.open()
        tof.start_ranging(SHORT_RANGE_MODE)
        return tof
    except Exception as e:
        logging.error(f"Error al inicializar el sensor en dirección {i2c_address}: {e}")
        print(f"Error al inicializar el sensor en dirección {i2c_address}: {e}")
        return None

def read_distance(tof, sensor_name, topic):
    try:
        distance = tof.get_distance()
        if distance < 10:  # Ignorar valores menores a 10 mm
            print(f"Distancia {sensor_name}: ignorada (menor a 10 mm)")
            logging.info(f"Distancia {sensor_name}: ignorada (menor a 10 mm)")
            return

        print(f"Distancia {sensor_name}: {distance} mm")
        logging.info(f"Distancia {sensor_name}: {distance} mm")

        # Publica la lectura en formato JSON
        payload = json.dumps({"value": distance})
        client.publish(topic, payload)
        print(f"Publicado en {topic}: {payload}")

    except Exception as e:
        print(f"Error al obtener distancia de {sensor_name}: {e}")
        logging.error(f"Error al obtener distancia de {sensor_name}: {e}")

def main():
    global error_count
    error_count = 0
    MAX_ERRORS = 3
    reset_gpio_1 = setup_gpio(RESET_PIN_1)
    reset_gpio_2 = setup_gpio(RESET_PIN_2)

    while True:
        try:
            # Sensor 1: Activar, leer y apagar
            print("Activando el sensor 1 en GPIOA6 (pin físico 12)...")
            reset_gpio_1.write(True)
            reset_gpio_2.write(False)
            time.sleep(0.3)
            tof_1 = initialize_sensor(I2C_ADDRESS, i2c_bus=0)

            if tof_1:
                print("Sensor 1 inicializado en 0x29")
                read_distance(tof_1, "Sensor 1", MQTT_TOPIC_1)
                tof_1.stop_ranging()
                tof_1.close()
                print("Sensor 1 apagado.")
            else:
                print("Error al inicializar el sensor 1.")
                error_count += 1

            reset_gpio_1.write(False)
            time.sleep(0.3)

            # Sensor 2: Activar, leer y apagar
            print("Activando el sensor 2 en GPIOC3 (pin físico 24)...")
            reset_gpio_1.write(False)
            reset_gpio_2.write(True)
            time.sleep(0.3)
            tof_2 = initialize_sensor(I2C_ADDRESS, i2c_bus=0)

            if tof_2:
                print("Sensor 2 inicializado en 0x29")
                read_distance(tof_2, "Sensor 2", MQTT_TOPIC_2)
                tof_2.stop_ranging()
                tof_2.close()
                print("Sensor 2 apagado.")
            else:
                print("Error al inicializar el sensor 2.")
                error_count += 1

            reset_gpio_2.write(False)
            time.sleep(0.3)

            # Si no hubo errores en esta iteración, restablece el contador
            if error_count == 0:
                continue

            # Incrementar error_count solo si hubo un error en esta iteración
            if error_count > 0:
                if error_count >= MAX_ERRORS:
                    logging.info(f"Demasiados errores ({error_count}), reiniciando el servicio sensor.service")
                    subprocess.run(["sudo", "systemctl", "restart", "sensor.service"], check=True)
                    error_count = 0  # Resetear el contador después de reiniciar
                else:
                    logging.warning(f"Error detectado, contador de errores: {error_count}")
                    time.sleep(5)  # Espera antes de continuar

        except Exception as e:
            logging.error(f"Error inesperado en el ciclo principal: {e}")
            print(f"Error inesperado: {e}. Esperando 5 segundos antes de continuar...")
            error_count += 1
            time.sleep(5)

if __name__ == "__main__":
    main()
