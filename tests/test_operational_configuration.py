import unittest
from unittest.mock import Mock
import requests
from backend_client import BackendClient


class OperationalConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.client = BackendClient('http://backend', 'test', start_workers=False, outbox_path=':memory:')
        self.addCleanup(self.client.close)
        self.profile = dict(camera_id='cam', id='profile', stream_url='https://camera/feed',
                            roi=dict(x=0, y=0, w=640, h=360),
                            line=dict(x1=0, y1=180, x2=640, y2=180), count_direction='down')

    def test_configuration_registration_precedes_activation_and_failed_registration_stops_it(self):
        self.client._session.post = Mock(return_value=Mock(status_code=409))
        self.assertFalse(self.client.notify_stream_profile_activated('cam', 'profile', configuration=self.profile))
        self.assertEqual(1, self.client._session.post.call_count)
        self.assertTrue(self.client._session.post.call_args.args[0].endswith('/camera-config'))

    def test_timeout_does_not_change_active_configuration_version(self):
        self.client.configuration_version = 'original'
        self.client._session.post = Mock(side_effect=requests.Timeout())
        self.assertFalse(self.client.register_operational_configuration(self.profile))
        self.assertEqual('original', self.client.configuration_version)

    def test_queued_event_retains_original_version_after_profile_changes(self):
        self.client._session.post = Mock(return_value=Mock(status_code=200, json=lambda: {'configurationVersion': 'v1'}))
        self.assertTrue(self.client.register_operational_configuration(self.profile))
        self.client.send_count_event({'cameraId': 'cam', 'roundId': 'round-old', 'trackId': '42'})
        self.client._session.post = Mock(return_value=Mock(status_code=200, json=lambda: {'configurationVersion': 'v2'}))
        self.assertTrue(self.client.register_operational_configuration(self.profile))
        sent = []
        self.client._session.post = Mock(side_effect=lambda url, **kw: (sent.append(kw['json']) or Mock(status_code=200, json=lambda: {'received': True})))
        self.client.deliver_pending_once()
        self.assertEqual('v1', sent[0]['configurationVersion'])
        self.assertEqual('round-old', sent[0]['roundId'])

    def test_success_without_version_is_not_accepted(self):
        self.client._session.post = Mock(return_value=Mock(status_code=200, json=lambda: {'saved': True}))
        self.assertFalse(self.client.register_operational_configuration(self.profile))
