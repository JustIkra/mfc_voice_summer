from __future__ import annotations

import gc
import os
from pathlib import Path
from typing import Any, Literal

import librosa
import numpy as np
import soundfile as sf
import torch
from fastapi import FastAPI, HTTPException
from faster_whisper import WhisperModel
from logging_config import get_logger
from pyannote.audio import Pipeline
from pydantic import BaseModel
from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

ASR_MODEL = os.getenv("ASR_MODEL", "large-v3-turbo")
DIARIZATION_MODEL = os.getenv("DIARIZATION_MODEL", "pyannote/speaker-diarization-3.1")
SER_MODEL = os.getenv(
    "SER_MODEL",
    "xbgoose/hubert-large-speech-emotion-recognition-russian-dusha-finetuned",
)
SERVICE = os.getenv("MODEL_SERVICE", "asr")
DEVICE = (
    "cuda"
    if os.getenv("MODEL_DEVICE", "cuda") == "cuda" and torch.cuda.is_available()
    else "cpu"
)

app = FastAPI(title=f"MFC Voice {SERVICE} API")
logger = get_logger()

_asr_model: WhisperModel | None = None
_diarization_pipeline: Pipeline | None = None
_emotion_extractor: AutoFeatureExtractor | None = None
_emotion_model: AutoModelForAudioClassification | None = None


class AudioRequest(BaseModel):
    path: str


class EmotionRequest(BaseModel):
    path: str
    diarization: list[dict[str, Any]]


def clear_cuda() -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()


def assert_service(expected: Literal["asr", "diarization", "emotion"]) -> None:
    if expected != SERVICE:
        raise HTTPException(status_code=404, detail=f"service is {SERVICE}, not {expected}")


def load_diarization_pipeline(token: str) -> Pipeline:
    try:
        pipeline = Pipeline.from_pretrained(DIARIZATION_MODEL, token=token)
    except TypeError:
        pipeline = Pipeline.from_pretrained(DIARIZATION_MODEL, use_auth_token=token)
    if pipeline is None:
        raise HTTPException(
            status_code=500,
            detail=f"could not load diarization model: {DIARIZATION_MODEL}",
        )
    if DEVICE == "cuda":
        pipeline.to(torch.device("cuda"))
    return pipeline


def safe_path(raw: str) -> Path:
    path = Path(raw)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"audio file not found: {raw}")
    return path


def read_audio(path: Path, target_sr: int = 16000) -> tuple[np.ndarray, int]:
    audio, sr = sf.read(path, always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    audio = audio.astype(np.float32)
    if sr != target_sr:
        audio = librosa.resample(audio, orig_sr=sr, target_sr=target_sr).astype(np.float32)
        sr = target_sr
    return audio, sr


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "service": SERVICE,
        "device": DEVICE,
        "cuda_available": torch.cuda.is_available(),
        "cuda_device_count": torch.cuda.device_count(),
    }


@app.post("/transcribe")
def transcribe(request: AudioRequest) -> dict[str, Any]:
    assert_service("asr")
    path = safe_path(request.path)
    global _asr_model
    if _asr_model is None:
        compute_type = "float16" if DEVICE == "cuda" else "int8"
        logger.info(
            "loading_asr_model model=%s device=%s compute_type=%s",
            ASR_MODEL,
            DEVICE,
            compute_type,
        )
        _asr_model = WhisperModel(ASR_MODEL, device=DEVICE, compute_type=compute_type)
        logger.info("loaded_asr_model")
    logger.info("transcribe_start path=%s", path)
    segments, info = _asr_model.transcribe(
        str(path),
        language="ru",
        task="transcribe",
        beam_size=5,
        vad_filter=True,
        condition_on_previous_text=True,
        word_timestamps=True,
    )
    transcript_segments = []
    for item in segments:
        text = item.text.strip()
        if not text:
            continue
        words = []
        for word in item.words or []:
            value = word.word.strip()
            if not value:
                continue
            words.append(
                {
                    "start": float(word.start),
                    "end": float(word.end),
                    "word": value,
                    "probability": float(word.probability),
                }
            )
        transcript_segments.append(
            {
                "start": float(item.start),
                "end": float(item.end),
                "text": text,
                "words": words,
            }
        )
    payload = {
        "model": ASR_MODEL,
        "language": info.language,
        "language_probability": info.language_probability,
        "segments": transcript_segments,
    }
    logger.info("transcribe_done path=%s segments=%s", path, len(payload["segments"]))
    return payload


@app.post("/diarize")
def diarize(request: AudioRequest) -> dict[str, Any]:
    assert_service("diarization")
    path = safe_path(request.path)
    token = os.getenv("HF_TOKEN")
    if not token:
        raise HTTPException(status_code=500, detail="HF_TOKEN is required")
    global _diarization_pipeline
    if _diarization_pipeline is None:
        logger.info(
            "loading_diarization_model model=%s device=%s",
            DIARIZATION_MODEL,
            DEVICE,
        )
        _diarization_pipeline = load_diarization_pipeline(token)
        logger.info("loaded_diarization_model")
    audio, sr = read_audio(path)
    waveform = torch.from_numpy(audio).unsqueeze(0)
    if DEVICE == "cuda":
        waveform = waveform.cuda()
    diarization_output = _diarization_pipeline(
        {"waveform": waveform, "sample_rate": sr},
        num_speakers=2,
    )
    annotation = getattr(
        diarization_output,
        "exclusive_speaker_diarization",
        getattr(diarization_output, "speaker_diarization", diarization_output),
    )
    del waveform
    clear_cuda()
    return {
        "model": DIARIZATION_MODEL,
        "segments": [
            {"start": float(turn.start), "end": float(turn.end), "speaker": str(speaker)}
            for turn, _, speaker in annotation.itertracks(yield_label=True)
        ],
    }


@app.post("/emotion")
def emotion(request: EmotionRequest) -> dict[str, Any]:
    assert_service("emotion")
    path = safe_path(request.path)
    global _emotion_extractor, _emotion_model
    if _emotion_extractor is None or _emotion_model is None:
        logger.info("loading_emotion_model model=%s device=%s", SER_MODEL, DEVICE)
        _emotion_extractor = AutoFeatureExtractor.from_pretrained(SER_MODEL)
        _emotion_model = AutoModelForAudioClassification.from_pretrained(SER_MODEL)
        if DEVICE == "cuda":
            _emotion_model = _emotion_model.cuda()
        _emotion_model.eval()
        logger.info("loaded_emotion_model")
    audio, sr = read_audio(path)
    min_len = int(0.25 * sr)
    result: list[dict[str, Any]] = []
    for segment in request.diarization:
        start_time = float(segment["start"])
        end_time = float(segment["end"])
        start = max(0, int(start_time * sr))
        end = min(len(audio), int(end_time * sr))
        chunk = audio[start:end]
        if len(chunk) < min_len:
            continue
        inputs = _emotion_extractor(chunk, sampling_rate=sr, return_tensors="pt", padding=True)
        if DEVICE == "cuda":
            inputs = {key: value.cuda() for key, value in inputs.items()}
        with torch.inference_mode():
            logits = _emotion_model(**inputs).logits[0]
            probs = torch.softmax(logits, dim=-1).detach().cpu().numpy()
        distribution = {
            _emotion_model.config.id2label[i]: float(probs[i])
            for i in range(len(probs))
        }
        label, score = max(distribution.items(), key=lambda item: item[1])
        result.append(
            {
                "start": start_time,
                "end": end_time,
                "speaker": str(segment["speaker"]),
                "label": label,
                "score": score,
                "distribution": distribution,
            }
        )
    clear_cuda()
    return {"model": SER_MODEL, "segments": result}
