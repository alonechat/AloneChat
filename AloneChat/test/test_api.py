import requests

# Try to get server address
url = 'http://localhost:8766/api/get_default_server'

try:
    response = requests.get(url)
    response.raise_for_status()  # If the status code is not 200 then raise error
    try:
        data = response.json()
        print('API respond:', data)
        if data.get('success'):
            print(f'Successfully get address: {data.get("default_server_address")}')
        else:
            print('Failed getting default server address!')
    except ValueError as e:
        print(f'JSON parsing error: {e}')
        print(f'Res text: {response.text}')
except requests.exceptions.RequestException as e:
    print(f'API invoke error: {e}')
    if 'response' in locals():
        # noinspection PyUnboundLocalVariable
        print(f'Text: {response.text}')
