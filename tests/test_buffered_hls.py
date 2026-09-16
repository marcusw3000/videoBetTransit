import os
import unittest
from unittest import mock

import cv2
import requests
from buffered_hls import BufferedHlsCapture, parse_media_playlist
from capture_backend import open_ffmpeg_capture

PLAYLIST = '#EXTM3U\n#EXT-X-TARGETDURATION:5\n#EXT-X-MEDIA-SEQUENCE:100\n' + ''.join(
    f'#EXTINF:5.0,\nsegment-{i}.ts\n' for i in range(4)) + '#EXT-X-ENDLIST\n'


class BufferedHlsTests(unittest.TestCase):
    def make_capture(self, **kwargs):
        with mock.patch('buffered_hls.threading.Thread'):
            return BufferedHlsCapture('https://example.com/live/index.m3u8', **kwargs)

    def test_media_sequence_relative_paths_and_end_of_stream(self):
        duration, segments, finished = parse_media_playlist(PLAYLIST, 'https://example.com/live/index.m3u8')
        self.assertEqual(duration, 5)
        self.assertEqual(segments[0], (100, 'https://example.com/live/segment-0.ts'))
        self.assertEqual(segments[-1][0], 103)
        self.assertTrue(finished)

    def test_unsupported_playlists_are_not_misdecoded(self):
        for line in ('#EXT-X-KEY:METHOD=AES-128,URI="key"', '#EXT-X-MAP:URI="init.mp4"',
                     '#EXT-X-BYTERANGE:123', '#EXT-X-STREAM-INF:BANDWIDTH=2000', 'file:///secret.ts'):
            with self.subTest(line=line), self.assertRaises(ValueError):
                parse_media_playlist('#EXTM3U\n' + line, 'https://example.com/live.m3u8')

    def test_prefetch_starts_at_last_three_segments_not_dvr_beginning(self):
        cap = self.make_capture()
        cap._get = mock.Mock(side_effect=[PLAYLIST.encode(), b'one', b'two', b'three'])
        cap._download()
        self.assertEqual(cap._queue.maxsize, 3)
        self.assertEqual(cap._queue.qsize(), 3)
        self.assertTrue(cap._get.call_args_list[1].args[1].endswith('segment-1.ts'))
        cap.release()

    def test_url_renewal_keeps_segment_sequence_and_does_not_replay(self):
        renew = mock.Mock(return_value='https://renewed.example/live/index.m3u8')
        cap = self.make_capture(refresh_url=renew)
        # Failure after the first downloaded segment: renewal must retry the
        # failed segment, not enqueue the first one a second time.
        cap._get = mock.Mock(side_effect=[PLAYLIST.encode(), b'one', requests.HTTPError(),
                                         PLAYLIST.encode(), b'two', b'three'])
        with mock.patch.object(cap._stop, 'wait', return_value=False):
            cap._download()
        renew.assert_called_once()
        self.assertEqual([cap._queue.get_nowait() for _ in range(3)], [b'one', b'two', b'three'])
        self.assertTrue(cap._get.call_args_list[4].args[1].endswith('segment-2.ts'))
        cap.release()

    def test_temporary_segment_is_released_and_removed(self):
        cap = self.make_capture()
        cap._queue.put(b'compressed-test-segment')
        decoder = mock.Mock()
        decoder.get.return_value = 30
        frame = object()
        decoder.read.return_value = (True, frame)
        with mock.patch('buffered_hls.open_ffmpeg_capture', return_value=decoder):
            self.assertEqual(cap.read(), (True, frame))
            path = cap._segment_path
            self.assertTrue(os.path.isfile(path))
            cap.release()
        decoder.release.assert_called_once()
        self.assertFalse(os.path.exists(path))

    def test_transfer_size_is_bounded(self):
        cap = self.make_capture()
        session = mock.MagicMock()
        response = session.get.return_value.__enter__.return_value
        response.iter_content.return_value = [b'1234', b'5678']
        with self.assertRaises(requests.Timeout):
            cap._get(session, cap.url, 6)
        cap.release()

    def test_native_options_are_restored_after_open(self):
        with mock.patch.dict(os.environ, {'OPENCV_FFMPEG_CAPTURE_OPTIONS': 'original'}):
            with mock.patch.object(cv2, 'VideoCapture') as constructor:
                constructor.side_effect = lambda *_: self.assertNotIn('OPENCV_FFMPEG_CAPTURE_OPTIONS', os.environ)
                open_ffmpeg_capture('segment.ts')
            self.assertEqual(os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'], 'original')


if __name__ == '__main__':
    unittest.main()
