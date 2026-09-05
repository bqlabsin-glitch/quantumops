from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from .models import PlatformEmailSettings
from .email_config import cipher, send_platform_email


class EmailConfigurationTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user('email-admin', email='admin@example.com', is_staff=True)
        self.api = APIClient()
        self.api.force_authenticate(self.admin)
        self.data = dict(enabled=True,host='smtp.example.com',port=587,username='mailer',password='private-test-value',security='STARTTLS',from_email='sender@example.com')

    def test_secret_is_encrypted_hidden_and_preserved(self):
        response=self.api.put('/api/platform-admin/email/', self.data, format='json')
        self.assertEqual(response.status_code,200)
        self.assertNotIn('private-test-value',str(response.data))
        stored=PlatformEmailSettings.objects.get()
        self.assertNotEqual(stored.password_encrypted,self.data['password'])
        self.assertEqual(cipher().decrypt(stored.password_encrypted.encode()).decode(),self.data['password'])
        self.data['password']=''
        self.api.put('/api/platform-admin/email/',self.data,format='json')
        stored.refresh_from_db()
        self.assertTrue(stored.password_encrypted)

    def test_member_and_anonymous_cannot_read_write_or_test(self):
        member=get_user_model().objects.create_user('ordinary')
        for user in (member,None):
            self.api.force_authenticate(user)
            self.assertEqual(self.api.get('/api/platform-admin/email/').status_code,403)
            self.assertEqual(self.api.put('/api/platform-admin/email/',self.data,format='json').status_code,403)
            self.assertEqual(self.api.post('/api/platform-admin/email/test/').status_code,403)

    def test_disabled_delivery_fails_without_smtp(self):
        PlatformEmailSettings.objects.create(enabled=False)
        with patch('ops.email_config.get_connection') as connection:
            with self.assertRaises(OSError):
                send_platform_email('test','test',['admin@example.com'])
            connection.assert_not_called()

    def test_test_email_targets_current_admin(self):
        with patch('ops.views.send_platform_email') as send:
            response=self.api.post('/api/platform-admin/email/test/',{'to':'other@example.com'},format='json')
            self.assertEqual(response.status_code,200)
            self.assertEqual(send.call_args.args[2],['admin@example.com'])

    def test_tls_and_validation(self):
        self.data['security']='NONE'
        self.assertEqual(self.api.put('/api/platform-admin/email/',self.data,format='json').status_code,400)
