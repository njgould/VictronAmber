import json
import datetime
import pytz
import requests
import matplotlib.pyplot as plt


now = datetime.datetime.now()

start = int(now.timestamp())
print (start)
# Max lookahead range is 24h
end = start + 86400

VRM_URL = "https://vrmapi.victronenergy.com/v2/installations/255790/stats"
VRM_TOKEN =  "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsImp0aSI6IjJmYWE5YjYyMjc4ODA4NTYxZTAwMWMwMTA2MGMzM2M1In0.eyJ1aWQiOiIyOTIxMzkiLCJ0b2tlbl90eXBlIjoicmVtZW1iZXJfbWUiLCJpc3MiOiJ2cm1hcGkudmljdHJvbmVuZXJneS5jb20iLCJhdWQiOiJodHRwczovL3ZybWFwaS52aWN0cm9uZW5lcmd5LmNvbS8iLCJpYXQiOjE3MTUyMDg3NzQsImV4cCI6MTczMDc2MDc3NCwianRpIjoiMmZhYTliNjIyNzg4MDg1NjFlMDAxYzAxMDYwYzMzYzUifQ.ocIKHCdX6IcvraQ8UzsQdlAF4-_Qhh8KRZrL5mQNW_ndsOprNrLLZz1OuqeBDMyA1Uscn002qlKX2_l62BR8cKsIromiDFKQiuQglWWwu0ZWzup54zgtzgRcYlakroAdmOG06-yIkBkfKPMwSHZ8348YMyLCNs1-95ZFqQb20T8aE0CTdeKk-vcYsI9ma0f1c5NIYr-7wKxzo24DrGNu6y3nXLqwmkNGP5_q_dAEAsWnTh4Z2mMn5W2b-sezh4S0jNAGDlWanaeEXT475JgFg_C2P0VOaxe6hVaSumvoEyGqarv3aeaEmLN_dd-fld63VrV1MCJEx3ub_n4k_G34sA"

headers = {
    'Accept': 'application/json',
    'x-authorization': f"Bearer {VRM_TOKEN}"
    }

params = {
    'type': 'forecast',
    # This works, but just returns null values for the non hour intervals - looks like 1 hr intervals only....
    # 'interval': '15mins',
    'start': start,
    'end': end,
    }

response = requests.get(VRM_URL, headers = headers, params = params, timeout=5)
vrm_data = response.json()


vrm_consumption_fc = vrm_data['records']['vrm_consumption_fc']
solar_yield_forecast = vrm_data['records']['solar_yield_forecast']

print (len(vrm_data['records']['solar_yield_forecast']))

plt.plot([datetime.datetime.fromtimestamp(i[0] / 1e3) for i in solar_yield_forecast],[i[1] for i in solar_yield_forecast])
plt.plot([datetime.datetime.fromtimestamp(i[0] / 1e3) for i in vrm_consumption_fc],[i[1] for i in vrm_consumption_fc])
plt.ylabel('Watts')
plt.xticks(rotation=45)
plt.show()
