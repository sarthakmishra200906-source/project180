"""Integration test: import the Flask `app` and exercise `/` and `/ai` endpoints."""

from server.app import app


def main():
    client = app.test_client()

    print('GET /')
    r = client.get('/')
    print('status:', r.status_code)

    print('\nPOST /ai')
    r2 = client.post('/ai', json={'prompt': 'Hello from integration test'})
    print('status:', r2.status_code)
    print('body:', r2.get_json())


if __name__ == '__main__':
    main()
