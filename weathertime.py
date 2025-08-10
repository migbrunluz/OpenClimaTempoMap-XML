from flask import Flask, request, Response
import requests
import csv
from datetime import datetime
import xml.etree.ElementTree as ET

app = Flask(__name__)

# Load city code map from Wayback cod_cidades.txt
CITY_MAP = {}

def load_city_map():
    url = "http://web.archive.org/web/20101125002706id_/http://webservice.climatempo.com.br:80/cod_cidades.txt"
    r = requests.get(url)
    lines = r.text.strip().splitlines()
    for line in lines:
        if ',' in line:
            parts = line.strip().split(',')
            if len(parts) >= 3:
                try:
                    code = int(parts[0])
                    name = parts[1].strip()
                    state = parts[2].strip()
                    CITY_MAP[code] = {'name': name, 'state': state}
                except ValueError:
                    continue

load_city_map()

ACCU_API_KEY = "43dde940b9f742238b90dba2c94c8a3f"
MSN_API_KEY = "j5i4gDqHL6nGYwx5wi5kRhXjtf2c5qgFX9fzfk0TOo"
MSN_USER = "m-31438E9A21C9613A37BC9B2C209E6070"

def get_latlon_accuweather(city, state):
    query = f"{city},{state}"
    url = f"https://api.accuweather.com/locations/v1/cities/search"
    params = {
        "apikey": ACCU_API_KEY,
        "q": query,
        "language": "pt-br",
        "details": "false"
    }
    r = requests.get(url, params=params, verify=False)
    if r.status_code == 200:
        results = r.json()
        if results:
            geo = results[0].get("GeoPosition", {})
            return geo.get("Latitude"), geo.get("Longitude")
    return None, None
 
@app.route("/ExibeXML.php")
def climatempo_route():
    from flask import request, Response
    import xml.etree.ElementTree as ET
    from datetime import datetime
    import requests

    # Manual weekday names in Portuguese
    WEEKDAYS_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

    OWM_TO_CLIMATEMPO_ICON = {
        "01d": "1r",    # clear sky day → sunny day
        "01n": "1rn",   # clear sky night → clear night
        "02d": "2r",    # few clouds day → partly cloudy day
        "02n": "2rn",   # few clouds night → partly cloudy night
        "03d": "3r",    # scattered clouds day → mostly cloudy day
        "03n": "3n",    # scattered clouds night → mostly cloudy night
        "04d": "2r",    # broken clouds day → intermittent clouds day
        "04n": "2rn",   # broken clouds night → intermittent clouds night (approx)
        "09d": "6r",    # shower rain day → showers day
        "09n": "6n",    # shower rain night → showers night
        "10d": "6r",    # rain day → rain day
        "10n": "6n",    # rain night → rain night
        "11d": "9tm",   # thunderstorm day → t-storms day
        "11n": "9tm",   # thunderstorm night → t-storms night
        "13d": "8r",    # snow day → snow day
        "13n": "8n",    # snow night → snow night
        "50d": "5r",    # mist day → fog/mist
        "50n": "5n",    # mist night → fog/mist
    }

    usuario = request.args.get("USUARIO")
    senha = request.args.get("SENHA")
    dias = request.args.get("DIAS")
    city_code_str = request.args.get("CODCIDADE")
    momento = request.args.get("MOMENTO", "").upper() == "TRUE"

    if usuario != "gigigoigo" or senha != "sdfuas9ksa":
        return Response("Unauthorized", status=401)
    if not momento and dias != "7":
        return Response("Only DIAS=7 supported when MOMENTO is not TRUE", status=400)
    if not city_code_str or not city_code_str.isdigit():
        return Response("Invalid or missing CODCIDADE", status=400)

    city_code = int(city_code_str)
    city_data = CITY_MAP.get(city_code)
    if not city_data:
        return Response("Invalid city code", status=404)

    city_name = city_data["name"]
    state = city_data["state"]

    lat, lon = get_latlon_accuweather(city_name, state)
    if not lat or not lon:
        return Response("Could not resolve location via AccuWeather", status=500)

    if momento:
        # Current moment weather
        owm_url = "https://api.openweathermap.org/data/2.5/weather"
        owm_params = {
            "lat": lat,
            "lon": lon,
            "units": "metric",
            "lang": "pt",
            "appid": "5796abbde9106b7da4febfae8c44c232"
        }
        resp = requests.get(owm_url, params=owm_params, verify=False)
        if resp.status_code != 200:
            return Response("OpenWeatherMap API error", status=502)
        try:
            data = resp.json()
        except Exception as e:
            return Response(f"Malformed response: {str(e)}", status=502)

        root = ET.Element("tempomomento")
        cidade_elem = ET.SubElement(root, "cidade", {
            "id": str(city_code),
        })

        ET.SubElement(cidade_elem, "temp").text = str(int(data.get("main", {}).get("temp", 0)))
        ET.SubElement(cidade_elem, "pressao").text = str(data.get("main", {}).get("pressure", "ND"))
        ET.SubElement(cidade_elem, "ventodir").text = str(data.get("wind", {}).get("deg", "ND"))
        wind_speed_kmh = int(data.get("wind", {}).get("speed", 0) * 3.6)
        ET.SubElement(cidade_elem, "ventoint").text = str(wind_speed_kmh)
        ET.SubElement(cidade_elem, "condicao").text = data.get("weather", [{}])[0].get("description", "ND").capitalize()

        # OpenWeatherMap current weather API doesn't include UVI here; could be fetched separately if needed
        ET.SubElement(cidade_elem, "ur").text = "ND"

        icon = data.get("weather", [{}])[0].get("icon", "")
        icon_code = OWM_TO_CLIMATEMPO_ICON.get(icon, "0")
        ET.SubElement(cidade_elem, "icone").text = icon_code

        dt_unix = data.get("dt", 0)
        if dt_unix:
            atualizacao = datetime.utcfromtimestamp(dt_unix).strftime("%H:%M")
        else:
            atualizacao = "ND"
        ET.SubElement(cidade_elem, "atualizacao").text = atualizacao

        xml_str = ET.tostring(root, encoding="utf-8", method="xml")
        return Response(xml_str, content_type="application/xml")

    else:
        # 7-day forecast
        owm_url = "https://api.openweathermap.org/data/2.5/onecall"
        owm_params = {
            "lat": lat,
            "lon": lon,
            "exclude": "current,minutely,hourly,alerts",
            "units": "metric",
            "lang": "pt",
            "appid": "5796abbde9106b7da4febfae8c44c232"
        }
        resp = requests.get(owm_url, params=owm_params, verify=False)
        if resp.status_code != 200:
            return Response("OpenWeatherMap API error", status=502)

        try:
            data = resp.json()
            forecasts = data.get("daily", [])
        except Exception as e:
            return Response(f"Malformed response: {str(e)}", status=502)

        root = ET.Element("previsao")
        cidades = ET.SubElement(root, "cidades")
        cidade_elem = ET.SubElement(cidades, "cidade", {
            "nome": city_name,
            "id": str(city_code),
            "estado": state
        })

        for day in forecasts[:7]:
            dt = day.get("dt")
            if not dt:
                continue

            date_obj = datetime.utcfromtimestamp(dt)
            date_fmt = date_obj.strftime("%d/%m/%Y")
            weekday = WEEKDAYS_PT[date_obj.weekday()]

            dia = ET.SubElement(cidade_elem, "data", {
                "diaprevisao": date_fmt,
                "nomedia": weekday
            })

            weather = day.get("weather", [{}])[0]
            full_summary = weather.get("description", "Sem descrição").capitalize()
            ET.SubElement(dia, "frase").text = full_summary
            ET.SubElement(dia, "frasereduzida").text = full_summary  # no short summary in OWM

            temp = day.get("temp", {})
            temp_lo = int(temp.get("min", 0))
            temp_hi = int(temp.get("max", 0))
            ET.SubElement(dia, "min").text = f"{temp_lo}°C"
            ET.SubElement(dia, "max").text = f"{temp_hi}°C"

            prob = int(day.get("pop", 0) * 100)  # probability of precipitation
            prec = day.get("rain", 0) or 0
            ET.SubElement(dia, "prob").text = f"{prob}%"
            ET.SubElement(dia, "prec").text = f"{prec}mm"

            icon_day = weather.get("icon", "")
            icon_code = OWM_TO_CLIMATEMPO_ICON.get(icon_day, "0")

            ET.SubElement(dia, "icomanha").text = icon_code
            ET.SubElement(dia, "icotarde").text = icon_code
            ET.SubElement(dia, "iconoite").text = icon_code
            ET.SubElement(dia, "icone").text = icon_code

            ET.SubElement(dia, "uv").text = str(day.get("uvi", "ND"))

            wind_deg = day.get("wind_deg", "ND")
            wind_speed = int(day.get("wind_speed", 0) * 3.6)  # convert m/s to km/h
            ET.SubElement(dia, "ventodir").text = str(wind_deg)
            ET.SubElement(dia, "ventomax").text = f"{wind_speed} km/h"
            ET.SubElement(dia, "ventoint").text = f"{int(wind_speed * 0.7)} km/h"  # approx avg

            rh = day.get("humidity", "ND")
            if isinstance(rh, int):
                ET.SubElement(dia, "umidade").text = f"{rh} %"
            else:
                ET.SubElement(dia, "umidade").text = "ND"

            sunrise = day.get("sunrise")
            sunset = day.get("sunset")
            try:
                if sunrise:
                    sunrise = datetime.utcfromtimestamp(sunrise).strftime("%Hh%M")
                else:
                    sunrise = "ND"
                if sunset:
                    sunset = datetime.utcfromtimestamp(sunset).strftime("%Hh%M")
                else:
                    sunset = "ND"
            except Exception:
                sunrise = "ND"
                sunset = "ND"

            ET.SubElement(dia, "solnascente").text = sunrise
            ET.SubElement(dia, "solpoente").text = sunset

        xml_str = ET.tostring(root, encoding="utf-8", method="xml")
        return Response(xml_str, content_type="application/xml")
if __name__ == "__main__":
    app.run(debug=True, port=80) 

