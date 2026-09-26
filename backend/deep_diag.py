"""
Deep diagnostic for the Groq Orpheus TTS white noise issue.
Run from: c:\Users\Ankit Jha\OneDrive\Desktop\tour_guide\backend
"""
import asyncio, httpx, struct, wave, io, os, sys
from dotenv import load_dotenv

load_dotenv('.env')
KEY = os.getenv('GROQ_API_KEY', '').strip()
BASE = 'https://api.groq.com/openai/v1'
MODEL = 'canopylabs/orpheus-v1-english'
VOICE = 'autumn'
TEXT  = 'In nineteen twenty-seven, Dr. Ambedkar led the Mahad Satyagraha.'

print("=" * 60)
print("GROQ ORPHEUS TTS — DEEP DIAGNOSTIC")
print("=" * 60)
print(f"API Key present: {bool(KEY)} ({KEY[:8]}...)" if KEY else "API Key: MISSING!")
print(f"Text to synthesise: {TEXT}")
print()

async def run():
    async with httpx.AsyncClient(
        base_url=BASE,
        headers={'Authorization': f'Bearer {KEY}'},
        timeout=30
    ) as c:
        print("STEP 1: Calling Groq TTS...")
        resp = await c.post('/audio/speech', json={
            'model': MODEL,
            'input': TEXT,
            'voice': VOICE,
            'response_format': 'wav',
        })
        print(f"  Status: {resp.status_code}")
        if resp.status_code != 200:
            print(f"  ERROR body: {resp.text}")
            return

        raw = resp.content
        print(f"  Raw bytes: {len(raw)}")
        print(f"  First 12 bytes hex: {raw[:12].hex()}")
        print(f"  RIFF tag: {raw[0:4]}")
        print(f"  WAVE tag: {raw[8:12]}")

        # Save raw response for inspection
        with open('diag_raw.wav', 'wb') as f:
            f.write(raw)
        print(f"  Saved: diag_raw.wav ({len(raw)} bytes)")

        print()
        print("STEP 2: Parsing WAV chunk structure...")
        pos = 12
        data_offset = None
        sample_rate = 24000
        while pos < len(raw) - 8:
            tag = raw[pos:pos+4]
            chunk_size = struct.unpack_from('<I', raw, pos+4)[0]
            print(f"  Chunk at byte {pos}: tag={tag} size={chunk_size:#010x} ({chunk_size})")
            if tag == b'fmt ':
                channels = struct.unpack_from('<H', raw, pos+8)[0]
                sample_rate = struct.unpack_from('<I', raw, pos+12)[0]
                bits = struct.unpack_from('<H', raw, pos+22)[0]
                print(f"    => channels={channels}, sample_rate={sample_rate}, bits={bits}")
            if tag == b'data':
                data_offset = pos + 8
                print(f"    => PCM starts at offset {data_offset}")
                if chunk_size == 0xFFFFFFFF:
                    print(f"    => Streaming mode (0xFFFFFFFF), PCM length = {len(raw) - data_offset}")
                break
            if chunk_size == 0xFFFFFFFF or chunk_size == 0:
                break
            pos += 8 + chunk_size

        print()
        print("STEP 3: Checking fast-path condition in current code...")
        condition = len(raw) > 78 and raw[70:74] == b'data'
        print(f"  len(raw) > 78: {len(raw) > 78}")
        print(f"  raw[70:74]: {raw[70:74]}")
        print(f"  Fast-path matches: {condition}")
        if condition:
            pcm_fastpath = raw[78:]
            print(f"  Fast-path PCM: {len(pcm_fastpath)} bytes")
        else:
            print("  WARNING: Fast-path MISS — falling back to chunk scan")
            if data_offset:
                pcm_fastpath = raw[data_offset:]
            else:
                pcm_fastpath = b''

        print()
        print("STEP 4: Repackaging as clean WAV...")
        if not pcm_fastpath:
            print("  ERROR: No PCM extracted!")
            return

        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_fastpath)
        clean = buf.getvalue()
        print(f"  Clean WAV size: {len(clean)} bytes")
        with open('diag_clean.wav', 'wb') as f:
            f.write(clean)
        print(f"  Saved: diag_clean.wav")

        print()
        print("STEP 5: Verifying clean WAV is readable...")
        try:
            with wave.open(io.BytesIO(clean), 'rb') as wf:
                print(f"  Channels: {wf.getnchannels()}")
                print(f"  Sample rate: {wf.getframerate()}")
                print(f"  Bit depth: {wf.getsampwidth() * 8}")
                print(f"  Frames: {wf.getnframes()}")
                print(f"  Duration: {wf.getnframes() / wf.getframerate():.2f}s")
        except Exception as e:
            print(f"  ERROR reading clean WAV: {e}")

        print()
        print("STEP 6: Tone fallback size check...")
        # The fallback WAV is always 384044 bytes — flag if that matches
        if len(clean) == 384044:
            print("  WARNING: Output is tone fallback size (384044 bytes)!")
        else:
            print(f"  OK: Output is real TTS audio ({len(clean)} bytes, not fallback)")

        print()
        print("=" * 60)
        print("DIAGNOSIS COMPLETE")
        print(f"  Play diag_raw.wav  — Groq's original output")
        print(f"  Play diag_clean.wav — After our PCM extraction")
        print("If diag_clean.wav sounds correct, the extraction is fine.")
        print("If diag_raw.wav sounds correct but diag_clean.wav doesn't,")
        print("the extraction offset is wrong.")
        print("=" * 60)

asyncio.run(run())
