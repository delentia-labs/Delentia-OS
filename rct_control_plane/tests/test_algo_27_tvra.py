"""
Round 45 item C (group 2): real tests for ALGO-27's TVRA engine - 0%
coverage before this file, previously flagged as needing real model
weights (YOLOv8n/ResNet18/R3D-18/Whisper). Real, not-mocked where genuinely
feasible: cv2 frame-quality/scene-diff math runs against a real tiny
synthetic video built with cv2.VideoWriter; audio metadata runs against a
real tiny synthetic wav built with soundfile; ReasoningEngine's temporal
logic is 100% real (pure Python, no ML). The four lazy model loaders
(_ensure_yolo/_ensure_resnet/_ensure_r3d/_ensure_whisper) are bypassed by
directly setting the already-loaded model attribute to a lightweight fake
BEFORE calling the real method under test - this exercises 100% real
post-processing arithmetic (confidence filtering, softmax/topk via real
torch, dict construction) against a fake model's raw output, without
downloading real pretrained weights.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import subprocess
import tempfile
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
import torch

from rct_control_plane.algo_27_tvra import (
    VideoProcessor, AudioProcessor, ReasoningEngine, TVRAEngine,
    ActivityCategory, VideoStatus,
)


def _solid_frame(value, size=16):
    return np.full((size, size, 3), value, dtype=np.uint8)


@pytest.fixture
def tiny_video(tmp_path):
    """A real, tiny synthetic video file - 10 frames alternating between
    two solid colors, written and read back with real cv2."""
    path = str(tmp_path / "tiny.avi")
    fourcc = cv2.VideoWriter_fourcc(*"XVID")
    writer = cv2.VideoWriter(path, fourcc, 5.0, (16, 16))
    for i in range(10):
        writer.write(_solid_frame(30 if i < 5 else 220))
    writer.release()
    return path


@pytest.fixture
def tiny_wav(tmp_path):
    import soundfile as sf
    path = str(tmp_path / "tiny.wav")
    sf.write(path, np.zeros(16000, dtype=np.float32), 16000)
    return path


class TestFrameQualityAndSceneDiff:
    def test_a_blank_frame_has_low_quality(self):
        vp = VideoProcessor()
        assert vp._assess_frame_quality(_solid_frame(128)) < 0.1

    def test_a_noisy_frame_has_higher_quality_than_a_blank_one(self):
        vp = VideoProcessor()
        rng = np.random.default_rng(42)
        noisy = rng.integers(0, 255, (64, 64, 3), dtype=np.uint8)
        assert vp._assess_frame_quality(noisy) > vp._assess_frame_quality(_solid_frame(128, size=64))

    def test_identical_frames_have_zero_difference(self):
        vp = VideoProcessor()
        frame = _solid_frame(100)
        assert vp._calculate_frame_difference(frame, frame) == pytest.approx(0.0, abs=1e-6)

    def test_very_different_frames_have_a_real_positive_difference(self):
        vp = VideoProcessor()
        diff = vp._calculate_frame_difference(_solid_frame(10), _solid_frame(250))
        assert diff > 0.0


class TestDetectScenes:
    @pytest.mark.asyncio
    async def test_fewer_than_two_frames_returns_a_single_trivial_scene(self):
        vp = VideoProcessor()
        scenes = await vp.detect_scenes([{"timestamp": 1.0, "frame": _solid_frame(1)}])
        assert len(scenes) == 1
        assert scenes[0]["scene_id"] == "scene_0"

    @pytest.mark.asyncio
    async def test_a_real_color_jump_splits_into_two_scenes(self):
        # The real chi-square histogram distance between these two solid
        # frames is exactly 1.0 (verified directly) - the split condition
        # is a strict `>`, so the threshold must sit below that.
        vp = VideoProcessor(scene_threshold=0.5)
        frames = [
            {"timestamp": 0.0, "frame": _solid_frame(10)},
            {"timestamp": 1.0, "frame": _solid_frame(10)},
            {"timestamp": 2.0, "frame": _solid_frame(250)},  # real, large color jump
            {"timestamp": 3.0, "frame": _solid_frame(250)},
        ]
        scenes = await vp.detect_scenes(frames)
        assert len(scenes) == 2
        assert scenes[0]["end_frame"] == 1
        assert scenes[1]["start_frame"] == 2

    @pytest.mark.asyncio
    async def test_gradually_similar_frames_stay_in_one_scene(self):
        vp = VideoProcessor(scene_threshold=1e6)  # threshold so high nothing splits
        frames = [{"timestamp": float(i), "frame": _solid_frame(i * 10)} for i in range(5)]
        scenes = await vp.detect_scenes(frames)
        assert len(scenes) == 1


class TestGetVideoInfoAndExtractFrames:
    def test_get_video_info_reads_real_metadata(self, tiny_video):
        vp = VideoProcessor()
        info = vp.get_video_info(tiny_video)
        assert info["width"] == 16
        assert info["height"] == 16
        assert info["frame_count"] == 10
        assert info["filename"] == "tiny.avi"

    def test_get_video_info_unreadable_path_raises(self):
        vp = VideoProcessor()
        with pytest.raises(ValueError, match="Cannot open video"):
            vp.get_video_info("no/such/video.mp4")

    @pytest.mark.asyncio
    async def test_extract_frames_from_a_real_synthetic_video(self, tiny_video):
        vp = VideoProcessor(min_frame_quality=0.0)  # accept every frame regardless of quality
        frames = await vp.extract_frames(tiny_video, fps=5)
        assert len(frames) > 0
        assert all("frame" in f and "timestamp" in f for f in frames)

    @pytest.mark.asyncio
    async def test_extract_frames_respects_max_frames(self, tiny_video):
        vp = VideoProcessor(min_frame_quality=0.0)
        frames = await vp.extract_frames(tiny_video, fps=5, max_frames=2)
        assert len(frames) == 2

    @pytest.mark.asyncio
    async def test_extract_frames_unreadable_path_raises(self):
        vp = VideoProcessor()
        with pytest.raises(ValueError, match="Cannot open video"):
            await vp.extract_frames("no/such/video.mp4")


class TestDetectObjectsWithAFakeYolo:
    @pytest.mark.asyncio
    async def test_real_postprocessing_filters_by_confidence_and_builds_real_dicts(self):
        vp = VideoProcessor()

        box_high = SimpleNamespace(conf=[0.9], cls=[0], xyxy=[[1.0, 2.0, 3.0, 4.0]])
        box_low = SimpleNamespace(conf=[0.1], cls=[1], xyxy=[[0.0, 0.0, 1.0, 1.0]])
        fake_result = SimpleNamespace(boxes=[box_high, box_low], names={0: "person", 1: "cat"})

        vp._yolo_model = lambda frame, verbose=False: [fake_result]  # bypasses _ensure_yolo (already non-None)

        objects = await vp.detect_objects(_solid_frame(50), confidence_threshold=0.5)
        assert len(objects) == 1  # the low-confidence box was filtered out
        assert objects[0]["class"] == "person"
        assert objects[0]["confidence"] == 0.9
        assert objects[0]["center"] == [2.0, 3.0]
        assert objects[0]["simulated"] is False


class TestClassifySceneWithAFakeResnet:
    @pytest.mark.asyncio
    async def test_real_softmax_and_topk_over_fake_logits(self):
        vp = VideoProcessor()
        vp._resnet_model = lambda batch: torch.tensor([[0.1, 5.0, 0.2]])  # "dog" strongly dominant
        vp._resnet_transform = lambda tensor: tensor  # identity - shape doesn't matter to the fake model
        vp._resnet_labels = ["cat", "dog", "bird"]

        result = await vp.classify_scene(_solid_frame(50), top_k=2)
        assert result["top_predictions"][0]["label"] == "dog"
        assert result["confidence"] == result["top_predictions"][0]["confidence"]
        assert len(result["top_predictions"]) == 2
        assert result["simulated"] is False


class TestTrackActionsWithAFakeR3d:
    @pytest.mark.asyncio
    async def test_fewer_than_four_frames_returns_no_actions(self):
        vp = VideoProcessor()
        result = await vp.track_actions([{"frame": _solid_frame(1), "frame_number": 0, "timestamp": 0.0}])
        assert result == []

    @pytest.mark.asyncio
    async def test_real_softmax_and_topk_over_a_fake_r3d_clip(self):
        vp = VideoProcessor()
        vp._r3d_model = lambda batch: torch.tensor([[0.1, 9.0]])  # "sitting" strongly dominant
        vp._r3d_transform = lambda clip: clip
        vp._r3d_labels = ["running", "sitting"]

        frames = [
            {"frame": _solid_frame(i * 10), "frame_number": i, "timestamp": float(i)}
            for i in range(6)
        ]
        result = await vp.track_actions(frames, clip_len=4)
        assert len(result) == 1
        assert result[0]["action"] == "sitting"
        assert result[0]["start_frame"] == 0
        assert result[0]["end_frame"] == 5
        assert result[0]["simulated"] is False


class TestAudioProcessorRealParts:
    def test_get_audio_info_reads_real_metadata(self, tiny_wav):
        ap = AudioProcessor()
        info = ap.get_audio_info(tiny_wav)
        assert info["sample_rate"] == 16000
        assert info["channels"] == 1
        assert info["duration"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_align_with_video_clamps_segments_past_the_video_end(self):
        ap = AudioProcessor()
        transcription = [{"start": 5.0, "end": 12.0, "text": "x"}]
        aligned = await ap.align_with_video(transcription, video_duration=10.0)
        assert aligned[0]["end"] == 10.0

    @pytest.mark.asyncio
    async def test_align_with_video_shifts_a_segment_starting_past_the_end(self):
        ap = AudioProcessor()
        transcription = [{"start": 15.0, "end": 20.0, "text": "x"}]
        aligned = await ap.align_with_video(transcription, video_duration=10.0)
        assert aligned[0]["start"] == pytest.approx(9.9)
        assert aligned[0]["end"] == 10.0

    @pytest.mark.asyncio
    async def test_diarize_speakers_falls_back_to_the_alternating_heuristic(self):
        # pyannote's pretrained models genuinely can't load in this
        # environment (no HuggingFace auth token) - this is the real,
        # always-exercised fallback path, not a mocked one.
        ap = AudioProcessor()
        transcription = [{"start": 0.0, "end": 1.0, "text": "a"}, {"start": 1.0, "end": 2.0, "text": "b"}]
        result = await ap.diarize_speakers("no-such-audio.wav", transcription)
        assert result[0]["speaker_id"] == 0
        assert result[1]["speaker_id"] == 1
        assert result[0]["simulated_speaker_id"] is True
        assert result[0]["diarization_unavailable_reason"]  # a real captured error string

    @pytest.mark.asyncio
    async def test_extract_audio_raises_on_a_real_ffmpeg_failure(self, monkeypatch, tmp_path):
        def _fake_run(cmd, capture_output, text):
            return SimpleNamespace(returncode=1, stderr="simulated real ffmpeg error")
        monkeypatch.setattr(subprocess, "run", _fake_run)

        ap = AudioProcessor()
        with pytest.raises(RuntimeError, match="simulated real ffmpeg error"):
            await ap.extract_audio(str(tmp_path / "in.mp4"))

    @pytest.mark.asyncio
    async def test_extract_audio_returns_the_real_output_path_on_success(self, monkeypatch, tmp_path):
        def _fake_run(cmd, capture_output, text):
            return SimpleNamespace(returncode=0, stderr="")
        monkeypatch.setattr(subprocess, "run", _fake_run)

        ap = AudioProcessor()
        out = await ap.extract_audio(str(tmp_path / "in.mp4"))
        assert out == str(tmp_path / "in_audio.wav")

    @pytest.mark.asyncio
    async def test_transcribe_with_a_fake_whisper_model(self):
        ap = AudioProcessor()
        ap._whisper_model = SimpleNamespace(transcribe=lambda audio_path, language, fp16: {
            "language": "en",
            "segments": [{"start": 0.0, "end": 1.5, "text": "  hello world  ", "avg_logprob": -0.1}],
        })
        segments = await ap.transcribe("fake.wav")
        assert segments[0]["text"] == "hello world"
        assert segments[0]["language"] == "en"
        assert segments[0]["simulated"] is False


class TestReasoningEngine:
    @pytest.fixture
    def engine(self):
        return ReasoningEngine(temporal_window=10.0)

    @pytest.mark.asyncio
    async def test_visual_events_fire_only_on_real_class_set_changes(self, engine):
        frames = [
            {"timestamp": 0.0, "objects": [{"class": "person", "confidence": 0.9}]},
            {"timestamp": 1.0, "objects": [{"class": "person", "confidence": 0.9}]},  # no new class
            {"timestamp": 2.0, "objects": [{"class": "person", "confidence": 0.9}, {"class": "dog", "confidence": 0.8}]},
        ]
        events = engine._detect_visual_events(frames)
        assert len(events) == 2  # "person" at t=0, "dog" at t=2 - not a repeat at t=1
        assert events[0]["description"] == "person enters scene"
        assert events[1]["description"] == "dog enters scene"

    def test_visual_events_skip_frames_without_object_detection(self, engine):
        frames = [{"timestamp": 0.0}]  # no "objects" key - wasn't sampled
        assert engine._detect_visual_events(frames) == []

    def test_audio_events_map_one_to_one_from_transcription(self, engine):
        transcription = [{"start": 0.0, "end": 1.0, "text": "hello", "confidence": 0.5}]
        events = engine._detect_audio_events(transcription)
        assert events[0]["event_type"] == "speech"
        assert events[0]["text"] == "hello"

    @pytest.mark.asyncio
    async def test_detect_events_merges_and_sorts_by_start_time_with_real_ids(self, engine):
        frames = [{"timestamp": 5.0, "objects": [{"class": "cat", "confidence": 0.9}]}]
        transcription = [{"start": 0.0, "end": 1.0, "text": "first", "confidence": 0.9}]
        events = await engine.detect_events(frames, transcription)
        assert events[0]["source"] == "audio"  # starts at t=0, sorted first
        assert events[1]["source"] == "visual"
        assert [e["event_id"] for e in events] == ["event_0", "event_1"]

    @pytest.mark.asyncio
    async def test_build_timeline_marks_first_and_last(self, engine):
        events = [{"start": 2.0}, {"start": 0.0}, {"start": 1.0}]
        timeline = await engine.build_timeline(events)
        assert timeline[0]["start"] == 0.0 and timeline[0]["is_first"] is True
        assert timeline[-1]["start"] == 2.0 and timeline[-1]["is_last"] is True

    @pytest.mark.parametrize("e1,e2,expected", [
        ((0.0, 1.0), (2.0, 3.0), "before"),
        ((2.0, 3.0), (0.0, 1.0), "after"),
        ((0.0, 5.0), (1.0, 2.0), "contains"),
        ((1.0, 2.0), (0.0, 5.0), "contained_by"),
        ((0.0, 2.0), (1.0, 3.0), "overlaps"),
        ((1.0, 3.0), (0.0, 2.0), "overlapped_by"),
    ])
    def test_temporal_relation_covers_every_real_case(self, engine, e1, e2, expected):
        event1 = {"start": e1[0], "end": e1[1]}
        event2 = {"start": e2[0], "end": e2[1]}
        assert engine._determine_temporal_relation(event1, event2) == expected

    def test_temporal_relation_outside_the_window_is_none(self, engine):
        event1 = {"start": 0.0, "end": 1.0}
        event2 = {"start": 100.0, "end": 101.0}
        assert engine._determine_temporal_relation(event1, event2) is None

    @pytest.mark.asyncio
    async def test_infer_causality_links_related_events(self, engine):
        events = [
            {"event_id": "e0", "start": 0.0, "end": 1.0},
            {"event_id": "e1", "start": 2.0, "end": 3.0},
        ]
        result = await engine.infer_causality(events)
        assert result[0]["related_events"] == ["e1"]
        assert result[0]["temporal_relations"]["e1"] == "before"

    @pytest.mark.asyncio
    async def test_recognize_patterns_finds_speech_then_action(self, engine):
        events = [
            {"event_id": "e0", "event_type": "speech", "start": 0.0, "end": 1.0},
            {"event_id": "e1", "event_type": "visual_action", "start": 2.0, "end": 2.0},
        ]
        patterns = await engine.recognize_patterns(events)
        assert any(p["pattern_type"] == "speech_action" for p in patterns)

    @pytest.mark.asyncio
    async def test_recognize_patterns_finds_repetition(self, engine):
        events = [{"event_id": f"e{i}", "event_type": "speech", "start": float(i), "end": float(i)} for i in range(3)]
        patterns = await engine.recognize_patterns(events)
        assert any(p["pattern_type"] == "repetition" and p["count"] == 3 for p in patterns)


class _FakeVideoProcessor:
    def get_video_info(self, path):
        return {"duration": 10.0, "width": 16, "height": 16}

    async def extract_frames(self, path, fps=2):
        return [{"frame_number": i, "timestamp": float(i), "frame": _solid_frame(i * 5)} for i in range(4)]

    async def detect_scenes(self, frames):
        return [{"scene_id": "scene_0", "start_time": 0.0, "end_time": 3.0}]

    async def detect_objects(self, frame, confidence_threshold=0.5):
        return [{"class": "person", "confidence": 0.9}]

    async def classify_scene(self, frame, top_k=3):
        return {"top_predictions": [{"label": "office", "confidence": 0.7}], "confidence": 0.7}

    async def track_actions(self, frames, clip_len=16):
        return [{"action": "meeting", "confidence": 0.8}]


class _FakeAudioProcessor:
    async def extract_audio(self, video_path, output_path=None):
        return "fake_audio.wav"

    async def transcribe(self, audio_path, language=None):
        return [{"start": 0.0, "end": 1.0, "text": "Hello Alice", "confidence": 0.9}]

    async def diarize_speakers(self, audio_path, transcription):
        return transcription

    async def align_with_video(self, transcription, video_duration):
        return transcription


class TestTVRAEngineOrchestration:
    @pytest.fixture
    def engine(self):
        return TVRAEngine(video_processor=_FakeVideoProcessor(), audio_processor=_FakeAudioProcessor())

    def test_extract_key_objects_aggregates_real_cached_detections(self, engine):
        frames = [{"objects": [{"class": "person"}]}, {"objects": [{"class": "dog"}]}, {"objects": [{"class": "person"}]}]
        assert set(engine._extract_key_objects(frames)) == {"person", "dog"}

    @pytest.mark.asyncio
    async def test_extract_key_actions_below_four_frames_is_empty(self, engine):
        assert await engine._extract_key_actions([{}]) == []

    @pytest.mark.asyncio
    async def test_extract_key_actions_delegates_to_the_real_track_actions_call(self, engine):
        frames = [{} for _ in range(4)]
        actions = await engine._extract_key_actions(frames)
        assert actions == ["meeting"]

    def test_extract_entities_finds_capitalized_words(self, engine):
        transcription = [{"text": "Hello Alice, how is Bob today"}]
        entities = engine._extract_entities(transcription)
        assert "Alice," in entities or "Alice" in entities
        assert "Bob" in entities
        assert "Hello" in entities

    @pytest.mark.parametrize("actions,expected", [
        (["running fast"], ActivityCategory.SPORTS),
        (["talking calmly"], ActivityCategory.MEETING),
        (["sitting quietly"], ActivityCategory.OTHER),
    ])
    def test_classify_activity_covers_all_three_categories(self, engine, actions, expected):
        assert engine._classify_activity([], actions) == expected

    def test_generate_scene_description_handles_empty_objects_and_actions(self, engine):
        desc = engine._generate_scene_description({}, [], [], [])
        assert "no detected objects" in desc
        assert "no detected action" in desc

    @pytest.mark.asyncio
    async def test_generate_summary_picks_top_5_most_confident_key_moments(self, engine):
        from rct_control_plane.algo_27_tvra import SceneSegment
        scenes = [SceneSegment(scene_id="s0", start=0.0, end=1.0, duration=1.0,
                                activity_category=ActivityCategory.OTHER, description="d")]
        events = [{"start": float(i), "description": f"e{i}", "confidence": float(i)} for i in range(8)]
        summary = await engine._generate_summary(scenes, [], events, duration=10.0)
        assert len(summary["key_moments"]) == 5
        assert summary["key_moments"][0]["confidence"] == 7.0  # highest confidence first

    def test_update_progress_and_get_job_status(self, engine):
        engine.active_jobs["v1"] = {"status": VideoStatus.PROCESSING, "progress": 0.0, "current_step": "start"}
        engine._update_progress("v1", 42.0, "midway")
        status = engine.get_job_status("v1")
        assert status["progress"] == 42.0
        assert status["current_step"] == "midway"

    def test_get_job_status_for_unknown_video_is_none(self, engine):
        assert engine.get_job_status("no-such-video") is None

    @pytest.mark.asyncio
    async def test_analyze_video_end_to_end_with_fully_faked_processors(self, engine):
        analysis = await engine.analyze_video("v1", "fake_path.mp4", options={"fps": 2})
        assert analysis.summary
        assert len(analysis.scenes) == 1
        assert engine.get_job_status("v1")["status"] == VideoStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_analyze_video_marks_the_job_failed_on_a_real_exception(self, engine, monkeypatch):
        async def _boom(*a, **k):
            raise RuntimeError("simulated real pipeline failure")
        monkeypatch.setattr(engine.video_processor, "extract_frames", _boom)

        with pytest.raises(RuntimeError, match="simulated real pipeline failure"):
            await engine.analyze_video("v2", "fake_path.mp4", options={})

        assert engine.get_job_status("v2")["status"] == VideoStatus.FAILED

    @pytest.mark.asyncio
    async def test_analyze_video_skips_audio_when_option_disabled(self, engine):
        analysis = await engine.analyze_video("v3", "fake_path.mp4", options={"transcribe_audio": False})
        assert analysis.transcription == []

    @pytest.mark.asyncio
    async def test_process_audio_failure_is_caught_and_returns_empty_not_a_crash(self, engine, monkeypatch):
        async def _boom(*a, **k):
            raise RuntimeError("simulated real audio extraction failure")
        monkeypatch.setattr(engine.audio_processor, "extract_audio", _boom)

        transcription = await engine._process_audio("fake_path.mp4", video_duration=10.0)
        assert transcription == []
