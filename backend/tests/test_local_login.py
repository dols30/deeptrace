"""Opt-in local sessions preserve employee identity and regular JWT authorization."""
import pytest
from fastapi.testclient import TestClient
from deeptrace.config import Settings, settings
from deeptrace.main import app
from deeptrace.auth import validate_access_token


@pytest.fixture
def configured(monkeypatch):
    for name,value in dict(local_auto_login=True,deployment_mode='local',auth_enabled=True,
                           auth_mode='employee',employee_username='local.employee',
                           employee_password='test-password',jwt_secret='test-secret-'*4).items():
        monkeypatch.setattr(settings,name,value)
    return TestClient(app,base_url='http://localhost:8000')


def test_local_login_uses_existing_identity_and_no_browser_password(configured):
    config=configured.get('/v1/auth/config')
    assert config.json()['local_auto_login'] is True
    assert 'test-password' not in config.text
    response=configured.post('/v1/auth/local-login',headers={'Origin':'http://localhost:3000'})
    assert response.status_code==200
    claims=validate_access_token(response.json()['access_token'])
    assert claims['sub']=='local.employee' and claims['role']=='analyst'
    assert response.json()['expires_in']==settings.token_minutes*60
    assert 'test-password' not in response.text
    assert configured.get('/v1/queue').status_code==401  # No blanket auth bypass.


@pytest.mark.parametrize('change',[dict(local_auto_login=False),dict(deployment_mode='sandbox'),dict(auth_mode='cognito'),dict(auth_enabled=False)])
def test_local_login_unavailable_outside_explicit_local_employee_mode(configured,monkeypatch,change):
    for name,value in change.items():monkeypatch.setattr(settings,name,value)
    assert configured.get('/v1/auth/config').json()['local_auto_login'] is False
    assert configured.post('/v1/auth/local-login').status_code==404


def test_nonlocal_host_and_cross_origin_cannot_obtain_local_session(configured):
    assert configured.post('/v1/auth/local-login',headers={'Host':'deeptrace.example'}).status_code==403
    assert configured.post('/v1/auth/local-login',headers={'Origin':'https://untrusted.example'}).status_code==403


@pytest.mark.parametrize('changes',[dict(deployment_mode='sandbox'),dict(auth_mode='cognito'),dict(auth_enabled=False),dict(jwt_secret='short')])
def test_settings_reject_unsafe_local_auto_login_profiles(changes):
    values=dict(local_auto_login=True,auth_enabled=True,auth_mode='employee',deployment_mode='local',
                employee_username='test',employee_password='test',jwt_secret='x'*32)
    values.update(changes)
    with pytest.raises(ValueError,match='Local automatic login'):
        Settings(_env_file=None,**values)


def test_local_auto_login_default_stays_off():
    assert Settings(_env_file=None).local_auto_login is False
