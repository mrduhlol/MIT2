import json

from app.models import AdminRole, SecurityEvent, SessionRecord
from tests.test_app import registered_user, auth_headers


def grant_admin(client, db):
    account = registered_user(client)
    db.add(AdminRole(user_id=account['user']['id']))
    db.commit()
    return account, auth_headers(account['token'])


def test_regular_users_cannot_access_admin_or_escalate(client):
    account = registered_user(client)
    headers = auth_headers(account['token'])
    assert account['user']['is_admin'] is False
    assert client.get('/api/admin/overview').status_code == 401
    for section in ('users', 'products', 'orders', 'sessions', 'api-keys', 'events'):
        assert client.get(f'/api/admin/records/{section}', headers=headers).status_code == 403
    assert client.patch(f"/api/admin/users/{account['user']['id']}", headers=headers, json={'is_active':False}).status_code == 403
    assert client.put('/api/me', headers=headers, json={'is_admin':True}).status_code == 400
    assert client.get('/api/me', headers=headers).json()['is_admin'] is False
    assert client.get('/api/admin/overview', headers=headers).status_code == 403


def test_admin_dashboards_redact_secrets_and_grants_are_checked_each_request(client, db):
    account, headers = grant_admin(client, db)
    assert client.get('/api/me', headers=headers).json()['is_admin'] is True
    assert client.get('/api/admin/overview', headers=headers).status_code == 200
    key = client.post('/api/api-keys', headers=headers, json={
        'name':'admin test', 'environment':'development', 'scopes':['security_events:read']
    }).json()
    for section in ('users', 'products', 'orders', 'sessions', 'api-keys', 'events'):
        response = client.get(f'/api/admin/records/{section}', headers=headers)
        assert response.status_code == 200
        assert 'columns' in response.json()
        assert key['secret'] not in response.text
        assert account['password'] not in response.text
        assert not any(name in response.text for name in ('hashed_password', 'hashed_secret', 'token_jti'))
    assert client.get('/api/admin/records/users?limit=101', headers=headers).status_code == 422
    assert client.get('/api/admin/records/unknown', headers=headers).status_code == 404
    db.delete(db.get(AdminRole, account['user']['id']))
    db.commit()
    assert client.get('/api/admin/overview', headers=headers).status_code == 403


def test_admin_controls_revoke_access_and_are_audited(client, db):
    admin, headers = grant_admin(client, db)
    target = registered_user(client)
    target_headers = auth_headers(target['token'])
    key = client.post('/api/api-keys', headers=target_headers, json={
        'name':'revoke test', 'environment':'development', 'scopes':['security_events:read']
    }).json()
    assert client.post(f"/api/admin/api-keys/{key['key']['id']}/revoke", headers=headers).status_code == 200
    assert client.get('/api/security/events', headers=auth_headers(key['secret'])).status_code == 401
    assert client.patch(f"/api/admin/users/{admin['user']['id']}", headers=headers, json={'is_active':False}).status_code == 403
    assert client.patch(f"/api/admin/users/{target['user']['id']}", headers=headers, json={'is_active':False}).status_code == 200
    assert client.get('/api/me', headers=target_headers).status_code == 401
    session = db.query(SessionRecord).filter_by(user_id=target['user']['id']).first()
    assert client.post(f'/api/admin/sessions/{session.id}/revoke', headers=headers).status_code == 200
    events=db.query(SecurityEvent).filter(SecurityEvent.pseudo_user==admin['user']['pseudo_id']).all()
    assert {'admin_user_status_changed','admin_api_key_revoked','admin_session_revoked'} <= {event.event_type for event in events}
    assert admin['password'] not in json.dumps([event.details for event in events])
