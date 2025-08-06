import requests

# 测试获取默认服务器地址API
url = 'http://localhost:8766/api/get_default_server'

try:
    response = requests.get(url)
    response.raise_for_status()  # 如果响应状态码不是200，抛出异常
    try:
        data = response.json()
        print('API响应:', data)
        if data.get('success'):
            print(f'成功获取默认服务器地址: {data.get("default_server_address")}')
        else:
            print('获取默认服务器地址失败')
    except ValueError as e:
        print(f'JSON解析错误: {e}')
        print(f'响应内容: {response.text}')
except requests.exceptions.RequestException as e:
    print(f'API调用错误: {e}')
    if 'response' in locals():
        # noinspection PyUnboundLocalVariable
        print(f'响应内容: {response.text}')
