"""Tests for :mod:`arxiv.users.auth.sessions.store`."""

from unittest import TestCase, mock
import time
import jwt
import json
from datetime import datetime
from redis.exceptions import ConnectionError

from .... import domain
from .. import store


class TestDistributedSessionService(TestCase):
    """The store session service puts sessions in a key-value store."""

    @mock.patch(f'{store.__name__}.redis')
    def test_create(self, mock_redis):
        """Accept a :class:`.User` and returns a :class:`.Session`."""
        mock_redis.exceptions.ConnectionError = ConnectionError
        mock_redis_connection = mock.MagicMock()
        mock_redis.StrictRedis.return_value = mock_redis_connection
        ip = '127.0.0.1'
        remote_host = 'foo-host.foo.com'
        user = domain.User(
            user_id=1,
            username='theuser',
            email='the@user.com'
        )
        auths = domain.Authorizations(
            classic=2,
            scopes=['foo:write'],
            endorsements=[]
        )
        r = store.SessionStore('localhost', 6379, 0, 'foosecret')
        session, cookie = r.create(user, auths, ip, remote_host)
        self.assertIsInstance(session, domain.Session)
        self.assertTrue(bool(session.session_id))
        self.assertIsNotNone(cookie)
        self.assertEqual(mock_redis_connection.set.call_count, 1)

    @mock.patch(f'{store.__name__}.redis')
    def test_delete(self, mock_redis):
        """Delete a session from the datastore."""
        mock_redis.exceptions.ConnectionError = ConnectionError
        mock_redis_connection = mock.MagicMock()
        mock_redis.StrictRedis.return_value = mock_redis_connection
        r = store.SessionStore('localhost', 6379, 0, 'foosecret')
        r.delete('fookey')
        self.assertEqual(mock_redis_connection.delete.call_count, 1)

    @mock.patch(f'{store.__name__}.redis')
    def test_connection_failed(self, mock_redis):
        """:class:`.SessionCreationFailed` is raised when creation fails."""
        mock_redis.exceptions.ConnectionError = ConnectionError
        mock_redis_connection = mock.MagicMock()
        mock_redis_connection.set.side_effect = ConnectionError
        mock_redis.StrictRedis.return_value = mock_redis_connection
        ip = '127.0.0.1'
        remote_host = 'foo-host.foo.com'
        user = domain.User(
            user_id=1,
            username='theuser',
            email='the@user.com'
        )
        auths = domain.Authorizations(
            classic=2,
            scopes=['foo:write'],
            endorsements=[]
        )
        r = store.SessionStore('localhost', 6379, 0, 'foosecret')
        with self.assertRaises(store.SessionCreationFailed):
            r.create(user, auths, ip, remote_host)


class TestGetSession(TestCase):
    """Tests for :func:`store.load`."""

    @mock.patch('arxiv.base.globals.flask_app')
    @mock.patch(f'{store.__name__}.redis.StrictRedis')
    def test_not_a_token(self, mock_get_redis, mock_app):
        """Something other than a JWT is passed."""
        mock_app.config = {
            'JWT_SECRET': 'barsecret',
            'REDIS_HOST': 'redis',
            'REDIS_PORT': '1234',
            'REDIS_DATABASE': 4
        }
        mock_redis = mock.MagicMock()
        mock_get_redis.return_value = mock_redis
        with self.assertRaises(store.InvalidToken):
            store.load('notatoken')

    @mock.patch('arxiv.base.globals.flask_app')
    @mock.patch(f'{store.__name__}.redis.StrictRedis')
    def test_malformed_token(self, mock_get_redis, mock_app):
        """A JWT with missing claims is passed."""
        secret = 'barsecret'
        mock_app.config = {
            'JWT_SECRET': secret,
            'REDIS_HOST': 'redis',
            'REDIS_PORT': '1234',
            'REDIS_DATABASE': 4
        }
        mock_redis = mock.MagicMock()
        mock_get_redis.return_value = mock_redis
        required_claims = ['session_id', 'nonce']
        for exc in required_claims:
            claims = {claim: '' for claim in required_claims if claim != exc}
            malformed_token = jwt.encode(claims, secret)
            with self.assertRaises(store.InvalidToken):
                store.load(malformed_token)

    @mock.patch('arxiv.base.globals.flask_app')
    @mock.patch(f'{store.__name__}.redis.StrictRedis')
    def test_token_with_bad_encryption(self, mock_get_redis, mock_app):
        """A JWT produced with a different secret is passed."""
        secret = 'barsecret'
        mock_app.config = {
            'JWT_SECRET': secret,
            'REDIS_HOST': 'redis',
            'REDIS_PORT': '1234',
            'REDIS_DATABASE': 4
        }
        mock_redis = mock.MagicMock()
        mock_get_redis.return_value = mock_redis
        claims = {
            'user_id': '1234',
            'session_id': 'ajx9043jjx00s',
            'nonce': '0039299290099'
        }
        bad_token = jwt.encode(claims, 'nottherightsecret')
        with self.assertRaises(store.InvalidToken):
            store.load(bad_token)

    @mock.patch('arxiv.base.globals.flask_app')
    @mock.patch(f'{store.__name__}.redis.StrictRedis')
    def test_expired_token(self, mock_get_redis, mock_app):
        """A JWT produced with a different secret is passed."""
        secret = 'barsecret'
        mock_app.config = {
            'JWT_SECRET': secret,
            'REDIS_HOST': 'redis',
            'REDIS_PORT': '1234',
            'REDIS_DATABASE': 4
        }
        now = (datetime.now() - datetime.utcfromtimestamp(0)).total_seconds()
        mock_redis = mock.MagicMock()
        mock_redis.get.return_value = json.dumps({
            'user_id': '1234',
            'session_id': 'ajx9043jjx00s',
            'nonce': '0039299290099',
            'start_time': datetime.now().isoformat(),
            'end_time': datetime.now().isoformat(),
        })
        mock_get_redis.return_value = mock_redis

        claims = {
            'user_id': '1234',
            'session_id': 'ajx9043jjx00s',
            'nonce': '0039299290099'
        }
        expired_token = jwt.encode(claims, secret)
        with self.assertRaises(store.InvalidToken):
            store.load(expired_token)

    @mock.patch('arxiv.base.globals.flask_app')
    @mock.patch(f'{store.__name__}.redis.StrictRedis')
    def test_forged_token(self, mock_get_redis, mock_app):
        """A JWT with the wrong nonce is passed."""
        secret = 'barsecret'
        mock_app.config = {
            'JWT_SECRET': secret,
            'REDIS_HOST': 'redis',
            'REDIS_PORT': '1234',
            'REDIS_DATABASE': 4
        }
        mock_redis = mock.MagicMock()
        mock_redis.get.return_value = json.dumps({
            'session_id': 'ajx9043jjx00s',
            'nonce': '0039299290098',
            'start_time': datetime.now().isoformat(),
            'user': {
                'user_id': '1235',
                'username': 'foouser',
                'email': 'foo@foo.com'
            }
        })
        mock_get_redis.return_value = mock_redis

        claims = {
            'user_id': '1234',
            'session_id': 'ajx9043jjx00s',
            'nonce': '0039299290099'    # <- Doesn't match!
        }
        expired_token = jwt.encode(claims, secret)
        with self.assertRaises(store.InvalidToken):
            store.load(expired_token)

    @mock.patch('arxiv.base.globals.flask_app')
    @mock.patch(f'{store.__name__}.redis.StrictRedis')
    def test_other_forged_token(self, mock_get_redis, mock_app):
        """A JWT with the wrong user_id is passed."""
        secret = 'barsecret'
        mock_app.config = {
            'JWT_SECRET': secret,
            'REDIS_HOST': 'redis',
            'REDIS_PORT': '1234',
            'REDIS_DATABASE': 4
        }
        mock_redis = mock.MagicMock()
        mock_redis.get.return_value = json.dumps({
            'session_id': 'ajx9043jjx00s',
            'nonce': '0039299290099',
            'start_time': datetime.now().isoformat(),
            'user': {
                'user_id': '1235',
                'username': 'foouser',
                'email': 'foo@foo.com'
            }
        })
        mock_get_redis.return_value = mock_redis

        claims = {
            'user_id': '1234',  # <- Doesn't match!
            'session_id': 'ajx9043jjx00s',
            'nonce': '0039299290099'
        }
        expired_token = jwt.encode(claims, secret)
        with self.assertRaises(store.InvalidToken):
            store.load(expired_token)

    @mock.patch('arxiv.base.globals.flask_app')
    @mock.patch(f'{store.__name__}.redis.StrictRedis')
    def test_empty_session(self, mock_get_redis, mock_app):
        """Session has been removed, or may never have existed."""
        secret = 'barsecret'
        mock_app.config = {
            'JWT_SECRET': secret,
            'REDIS_HOST': 'redis',
            'REDIS_PORT': '1234',
            'REDIS_DATABASE': 4
        }
        mock_redis = mock.MagicMock()
        mock_redis.get.return_value = ''    # <- Empty record!
        mock_get_redis.return_value = mock_redis

        claims = {
            'user_id': '1234',
            'session_id': 'ajx9043jjx00s',
            'nonce': '0039299290099',
        }
        expired_token = jwt.encode(claims, secret)
        with self.assertRaises(store.SessionUnknown):
            store.load(expired_token)

    @mock.patch('arxiv.base.globals.flask_app')
    @mock.patch(f'{store.__name__}.redis.StrictRedis')
    def test_valid_token(self, mock_get_redis, mock_app):
        """A valid token is passed."""
        secret = 'barsecret'
        mock_app.config = {
            'JWT_SECRET': secret,
            'REDIS_HOST': 'redis',
            'REDIS_PORT': '1234',
            'REDIS_DATABASE': 4
        }
        mock_redis = mock.MagicMock()
        mock_redis.get.return_value = json.dumps({
            'session_id': 'ajx9043jjx00s',
            'start_time': datetime.now().isoformat(),
            'nonce': '0039299290098',
            'user': {
                'user_id': '1234',
                'username': 'foouser',
                'email': 'foo@foo.com'
            }
        })
        mock_get_redis.return_value = mock_redis

        claims = {
            'user_id': '1234',
            'session_id': 'ajx9043jjx00s',
            'nonce': '0039299290098'
        }
        expired_token = jwt.encode(claims, secret)

        session = store.load(expired_token)
        self.assertIsInstance(session, domain.Session, "Returns a session")
