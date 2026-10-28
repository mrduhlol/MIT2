"""Verify an admin login and all dashboard APIs without printing credentials."""
import argparse
import getpass
import httpx

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base-url', required=True)
parser.add_argument('--email', required=True)
args = parser.parse_args()
password = getpass.getpass('Administrator password: ')
with httpx.Client(base_url=args.base_url, timeout=120) as client:
    response = client.post('/api/auth/login', json={'email': args.email, 'password': password})
    assert response.status_code == 200, f'Login HTTP {response.status_code}'
    payload = response.json()
    assert payload['user']['is_admin'] is True
    client.headers['Authorization'] = 'Bearer ' + payload['access_token']
    print('PASS administrator login and role', flush=True)
    for path in ['/api/admin/overview'] + [f'/api/admin/records/{name}' for name in ('users','products','orders','sessions','api-keys','events')]:
        response = client.get(path)
        assert response.status_code == 200, f'{path} HTTP {response.status_code}'
        assert all(value not in response.text for value in ('hashed_password','hashed_secret','token_jti',password))
        print('PASS', path, flush=True)
    response = client.post('/api/auth/logout')
    assert response.status_code == 200, f'Logout HTTP {response.status_code}'
    assert client.get('/api/admin/overview').status_code == 401
    print('PASS admin logout revokes dashboard access', flush=True)
