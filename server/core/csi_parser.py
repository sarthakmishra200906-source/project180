import json
import statistics

def parse_frame(raw_bytes):
    """Parse a JSON CSI frame produced by the local simulator.

    Returns a dict with keys: frame_id, ts, csi (list), amplitude_mean
    """
    try:
        obj = json.loads(raw_bytes.decode('utf-8'))
    except Exception:
        return None

    csi = obj.get('csi', [])
    amp_mean = None
    if csi:
        try:
            amp_mean = statistics.mean([abs(float(x)) for x in csi])
        except Exception:
            amp_mean = None

    return {
        'frame_id': obj.get('frame_id'),
        'ts': obj.get('ts'),
        'csi_len': len(csi),
        'amplitude_mean': amp_mean,
    }
