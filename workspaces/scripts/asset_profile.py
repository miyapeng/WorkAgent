"""Native asset inspection: structural facts and fallible visual observations stay separate."""
import json
import subprocess
from pathlib import Path
from urllib.parse import urlsplit
from common import require, sha256, save
from profile_files import profile, add_segment_ids
from vision import inspect_visual


def media_metadata(path):
    result=subprocess.run(['ffprobe','-v','error','-protocol_whitelist','file,pipe','-show_streams','-show_format','-of','json',str(path)],capture_output=True,text=True,timeout=30)
    require(result.returncode==0,'unreadable_media')
    data=json.loads(result.stdout);streams=data['streams']
    video=[s for s in streams if s.get('codec_type')=='video'];require(video,'no_video_stream')
    v=video[0];duration=float(data.get('format',{}).get('duration',v.get('duration',0)))
    require(duration>0 and v['width']>0 and v['height']>0,'invalid_video_dimensions_or_duration')
    return {'duration_seconds':duration,'width':v['width'],'height':v['height'],'codec':v['codec_name'],
            'frame_rate':v.get('avg_frame_rate'),'audio_streams':sum(s.get('codec_type')=='audio' for s in streams),
            'audio_content_inspected':False}


def inspect_asset(path,url,mime,cache,vision,offline=False):
    path=Path(path);data=path.read_bytes();h=sha256(data);suffix=Path(urlsplit(url).path).suffix.lower()
    if mime.startswith('video/') or suffix in ('.mp4','.mov','.webm') or data[4:8]==b'ftyp':
        info=media_metadata(path)
        p={'file_id':'f_'+h[:24],'sha256':h,'type':'video','format':suffix.lstrip('.') or 'mp4','parse_status':'parsed','structure':info,'segments':[
            {'locator':'container','text':json.dumps(info,sort_keys=True),'evidence_method':'programmatic_extraction'}],
            'warnings':['sampled_frames_do_not_establish_complete_temporal_or_audio_understanding'],'risk_signals':[]}
        directory=cache/'frames'/h;directory.mkdir(parents=True,exist_ok=True)
        # A small reproducible coverage grid, not a claim that events between samples were observed.
        times=[round(info['duration_seconds']*f,3) for f in (.05,.35,.65,.95)]
        for t in times:
            frame=directory/(str(t)+'.png')
            if not frame.exists():
                result=subprocess.run(['ffmpeg','-v','error','-protocol_whitelist','file,pipe','-ss',str(t),'-i',str(path),'-frames:v','1','-vf','scale=960:-2','-y',str(frame)],capture_output=True,timeout=30)
                require(result.returncode==0 and frame.exists(),'video_frame_decode_failed')
            fp=profile(frame,'https://local.invalid/frame.png','image/png',cache)
            if vision:
                try:fp=inspect_visual(frame.read_bytes(),fp,vision,cache,offline)
                except (OSError,ValueError,KeyError,TypeError) as exc:
                    p['warnings'].append(f'frame:{t}:visual_inspection_failed:'+str(exc))
            for s in fp.get('segments',[]):
                if s.get('evidence_method')=='model_visual_observation':
                    p['segments'].append({k:v for k,v in s.items() if k not in ('segment_id','verification_status')}|{'locator':f'frame:{t}:'+s['locator'],'timestamp_seconds':t,'frame_sha256':sha256(frame.read_bytes())})
        p['structure']['sampled_timestamps']=times
        return add_segment_ids(p)
    if suffix in ('.obj','.gltf','.glb','.stl','.blend'):
        # Do not claim spatial content was inspected merely because a native 3D file downloaded.
        return {'file_id':'f_'+h[:24],'sha256':h,'parse_status':'rejected','reason':'native_3d_geometry_inspector_not_implemented_use_inspectable_reference_views'}
    p=profile(path,url,mime,cache)
    if p.get('parse_status')!='parsed':return p
    if p['type'] in ('image','pdf') and vision:
        try:p=inspect_visual(data,p,vision,cache,offline)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            p['warnings'].append('visual_inspection_failed:'+str(exc));p['visual_failure']=str(exc)
    return p
