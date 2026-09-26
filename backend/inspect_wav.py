import os, asyncio, httpx, struct, wave, io
from dotenv import load_dotenv
load_dotenv('.env')
key = os.getenv('GROQ_API_KEY','').strip()

async def test():
    async with httpx.AsyncClient(base_url='https://api.groq.com/openai/v1', headers={'Authorization': f'Bearer {key}'}, timeout=30) as c:
        r = await c.post('/audio/speech', json={'model':'canopylabs/orpheus-v1-english','input':'Hello test nineteen twenty seven.','voice':'autumn','response_format':'wav'})
        raw = r.content
        print(f'Total bytes: {len(raw)}')
        print(f'RIFF tag: {raw[0:4]}')
        size_field = struct.unpack_from('<I', raw, 4)[0]
        print(f'File size field: {size_field:#010x}')
        print(f'WAVE tag: {raw[8:12]}')
        pos = 12
        fmt_sample_rate = None
        while pos < len(raw) - 8:
            tag = raw[pos:pos+4]
            chunk_size = struct.unpack_from('<I', raw, pos+4)[0]
            print(f'  Chunk at {pos}: tag={tag} size={chunk_size:#010x} ({chunk_size})')
            if tag == b'fmt ':
                fmt_sample_rate = struct.unpack_from('<I', raw, pos+12)[0]
                bits = struct.unpack_from('<H', raw, pos+22)[0]
                ch = struct.unpack_from('<H', raw, pos+10)[0]
                print(f'    => channels={ch}, sample_rate={fmt_sample_rate}, bits={bits}')
            if tag == b'data':
                pcm_start = pos + 8
                if chunk_size == 0xFFFFFFFF:
                    print(f'  Streaming size! PCM start={pcm_start}, PCM bytes={len(raw)-pcm_start}')
                    pcm_bytes = raw[pcm_start:]
                else:
                    pcm_bytes = raw[pcm_start:pcm_start+chunk_size]
                print(f'  PCM bytes extracted: {len(pcm_bytes)}')
                sr = fmt_sample_rate or 24000
                buf = io.BytesIO()
                with wave.open(buf, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sr)
                    wf.writeframes(pcm_bytes)
                print(f'  Clean WAV size: {len(buf.getvalue())}')
                with open('test_clean.wav', 'wb') as f:
                    f.write(buf.getvalue())
                print('  Written test_clean.wav')
                break
            if chunk_size == 0xFFFFFFFF:
                break
            pos += 8 + chunk_size

asyncio.run(test())
