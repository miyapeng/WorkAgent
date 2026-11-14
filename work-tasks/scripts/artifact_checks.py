"""Bounded native-artifact parsing, never execution or a claim of task correctness."""
import io
import json
import math
import struct
from html.parser import HTMLParser
from task_common import require
from profile_files import checked_zip
from asset_profile import media_metadata


FORMATS={'html','zip','mp4','mov','webm','obj','gltf','glb','stl'}


def inspect_output(path,fmt):
    if fmt in ('mp4','mov','webm'):
        metadata=media_metadata(path)
        require(metadata['width']>=2 and metadata['height']>=2,'invalid_video')
        return metadata
    raw=path.read_bytes();require(raw,'empty_artifact')
    if fmt=='html':
        class Tags(HTMLParser):
            def __init__(self):super().__init__();self.tags=set();self.content=[]
            def handle_starttag(self,tag,attrs):self.tags.add(tag)
            def handle_data(self,data):self.content.append(data)
        p=Tags();p.feed(raw.decode('utf-8-sig'))
        require('html' in p.tags and 'body' in p.tags and ''.join(p.content).strip(),'empty_or_invalid_html')
        return {'tags':sorted(p.tags),'scripts_executed':False}
    if fmt=='zip':
        with checked_zip(raw) as z:
            entries=[i for i in z.infolist() if not i.is_dir() and i.file_size]
            require(entries,'empty_archive')
            for entry in entries:z.read(entry) # Checks CRC; no extraction or execution.
            return {'entries':[i.filename for i in entries],'scripts_executed':False}
    if fmt=='obj':
        vertices=[];faces=[]
        for line in raw.decode('utf-8-sig').splitlines():
            parts=line.split()
            if parts and parts[0]=='v':
                require(len(parts)>=4,'invalid_obj_vertex');v=list(map(float,parts[1:4]));require(all(map(math.isfinite,v)),'nonfinite_geometry');vertices.append(v)
            if parts and parts[0]=='f':
                indices=[int(x.split('/')[0]) for x in parts[1:]];require(len(indices)>=3 and all(i!=0 for i in indices),'invalid_obj_face');faces.append((indices,len(vertices)))
        require(vertices and faces,'empty_geometry')
        require(all(all(0<i<=len(vertices) or -at<=i<0 for i in face) for face,at in faces),'obj_vertex_reference_missing')
        return {'vertices':len(vertices),'faces':len(faces)}
    if fmt in ('gltf','glb'):
        if fmt=='glb':
            require(len(raw)>=20 and raw[:4]==b'glTF','invalid_glb')
            version,length,size,kind=struct.unpack_from('<IIII',raw,4)
            require(version==2 and length==len(raw) and kind==0x4e4f534a and 20+size<=len(raw),'invalid_glb_header')
            data=json.loads(raw[20:20+size])
        else:data=json.loads(raw)
        require(data.get('asset',{}).get('version')=='2.0' and data.get('meshes') and data.get('accessors'),'empty_gltf')
        require(all(not b.get('uri') or b['uri'].startswith('data:') for b in data.get('buffers',[])),'external_gltf_buffer_requires_bundle')
        require(all(m.get('primitives') for m in data['meshes']),'empty_mesh')
        return {'meshes':len(data['meshes']),'geometry_validation':'structure_only'}
    if fmt=='stl':
        require(len(raw)>=84,'invalid_binary_stl');n=struct.unpack_from('<I',raw,80)[0]
        require(n>0 and len(raw)==84+50*n,'invalid_binary_stl_length')
        require(all(math.isfinite(x) for i in range(n) for x in struct.unpack_from('<12f',raw,84+50*i)),'nonfinite_geometry')
        return {'triangles':n}
    raise ValueError('unsupported_asset_format')
