import socket
import multitask
from app.voip import *
from std.rfc4566 import SDP, attrs as format

from subprocess import Popen, PIPE, STDOUT
import sys
WIN32= sys.platform == 'win32'

try:
    from subprocess import DEVNULL # py3k
except ImportError:
    import os
    DEVNULL = open(os.devnull, 'wb')

import logging
from logging import FileHandler, StreamHandler, config

#logging.basicConfig(level=logging.DEBUG)

# default_formatter = logging.Formatter("%(asctime)s|%(name)s|%(lineno)s|%(levelname)s|%(message)s")
# console_handler = StreamHandler()
# console_handler.setFormatter(default_formatter)
# log = logging.getLogger()
# log.addHandler(console_handler)
# log.setLevel(logging.INFO)

logging.config.fileConfig('logging.conf')
log = logging.getLogger()

sdp = '''v=0\r
o=- 1439521303 1439521303 IN IP4 10.17.41.163\r
s=-\r
c=IN IP4 10.17.41.163\r
t=0 0\r
m=audio 0 RTP/AVP 120 109 127 108 18 8 101 102\r
m=video 45900 RTP/AVP 34\r
a=fmtp:34 CIF=2 QCIF=2 MaxBR=2560
a=sendonly\r
'''
sdp = '''v=0\r
o=- 1439521303 1439521303 IN IP4 10.17.41.163\r
s=-\r
c=IN IP4 10.17.41.163\r
t=0 0\r
m=audio 0 RTP/AVP 120 109 127 108 18 8 101 102\r
m=video 45900 RTP/AVP 122\r
a=rtpmap:122 H264/90000\r
a=fmtp:122 profile-level-id=64E00C;max-br=384;packetization-mode=1\r
a=sendonly\r
'''
sdp = '''v=0\r
o=iue0 3203 3203 IN IP4 192.168.36.86\r
s=-\r
c=IN IP4 192.168.36.86\r
t=0 0\r
m=audio 2340 RTP/AVP 108\r
a=rtpmap:108 iLBC/8000\r
a=fmtp:108 mode=20\r
a=sendonly\r
m=video 45900 RTP/AVP 122\r
a=rtpmap:122 H264/90000\r
a=fmtp:122 profile-level-id=42E00C;max-br=384;packetization-mode=1\r
a=sendonly\r
'''
sdp = '''v=0\r
o=iue0 3203 3203 IN IP4 192.168.36.86\r
s=-\r
c=IN IP4 192.168.36.86\r
t=0 0\r
m=audio 2340 RTP/AVP 109\r
a=rtpmap:109 opus/16000\r
a=sendonly\r
m=video 45900 RTP/AVP 122\r
a=rtpmap:122 H264/90000\r
a=fmtp:122 profile-level-id=64E016;max-br=640\r
a=sendonly\r
'''

ip = '0.0.0.0'

def register(username, password, media=None):
  sock = socket.socket(type=socket.SOCK_DGRAM)
  sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  sock.bind((ip, 0))

  user = User(sock, nat=False).start()
  #user = User(sock, nat=True).start()
  result, reason = yield user.bind('<sip:' + username + '>', username=username, password=password, interval = 3600, refresh=True)
  log.info('user.bind() returned %s %s : %s', result, reason, username)

  multitask.add(autoAnswer(user, media))
	
def getMediaStreams():
  audio, video = SDP.media(media='audio'), SDP.media(media='video')			
  audio.fmt = [format(pt=8, name='PCMA', rate=8000)]
  video.fmt = [format(pt=34, name='H263', rate=90000)]
  #video.fmt = [format(pt=122, name='H264', rate=90000)]
  #video.a = ['fmtp:122 profile-level-id=64E00C;max-br=384']
  return (audio, video)
  
def autoAnswer(user, media = None, timeout = 5):
  while True:
    cmd, arg = (yield user.recv())
    if cmd == 'connect':
      log.info('incoming call from %s', arg)
			
      dest, ua = arg
      streams = getMediaStreams()	
      msession = MediaSession(app=user, streams=streams, request=ua.request)		
      yoursdp, mysdp = msession.yoursdp, msession.mysdp
      yourself, arg = yield user.accept(arg, sdp=sdp)
      if not yourself:
        log.info('cannot accept call %s', arg)
        continue		
      elif yourself.yoursdp:#late offer
        yoursdp = yourself.yoursdp
      log.info('REMOTE=%s:%d', yoursdp['c'].address, [m for m in yoursdp['m'] if m.media=='video'][0].port)		
      host, port = yoursdp['c'].address, [m for m in yoursdp['m'] if m.media=='video'][0].port
	  
      if media:
        cmd = ['ffmpeg', '-i', media, '-vcodec', 'h264', '-an', '-b:v', '640k', '-pix_fmt', 'yuv420p', '-payload_type', '122', '-s', '320*240', '-r', '20', '-profile:v', 'baseline', '-level', '1.2', '-f', 'rtp', 'rtp://' + host + ':' + str(port)]
      elif WIN32:
        media = 'video=Integrated Camera'
        cmd = ['ffmpeg.exe', '-f', 'dshow', '-i', media, '-vcodec', 'h264', '-b:v', '90000', '-pix_fmt', 'yuv420p', '-payload_type', '122', '-s', '320*240', '-r', '20', '-profile:v', 'baseline', '-level', '1.2', '-f', 'rtp', 'rtp://' + host + ':' + str(port)]
      else:	
        media = '/dev/video0'
        cmd = ['ffmpeg', '-f', 'video4linux2', '-i', media, '-vcodec', 'h264', '-b:v', '90000', '-pix_fmt', 'yuv420p', '-payload_type', '122', '-s', '320*240', '-r', '20', '-profile:v', 'baseline', '-level', '1.2', '-f', 'rtp', 'rtp://' + host + ':' + str(port)]
      
      log.info(' '.join(cmd))
      p = Popen(cmd, stdout=DEVNULL, stderr=DEVNULL)	  
      while True:
        try:	  
          cmd, arg = yield yourself.recv(timeout=timeout)
          log.debug('received command %s %s', cmd, arg)
        except multitask.Timeout:
          pass
        code = p.poll()			
        if cmd == 'close':
          if p:
            try:		  
              p.kill()
            except Exception:
              pass			
            p = None
          log.info('incoming call cancelled')	  
          break
        elif code is not None:
          log.info('ffmpeg return %s, bye', code)
          ua.sendRequest(ua.createRequest('BYE'))
          try: response = yield ua.queue.get(timeout=5) # wait for atmost 5 seconds for BYE response
          except multitask.Timeout: pass # ignore the no response for BYE
          #ua.close()  # this will remove dialog if needed
          break

    elif cmd == 'close':
      log.info('incoming call cancelled by %s', arg)
    elif cmd == 'send':
      log.info('paging-mode IM received %s', arg)	


if __name__ == '__main__':
  try:
    argv = sys.argv
    i, username, password, media = 1, None, None, None
    while i < len(argv):
      if argv[i] == '-u':
        if username:		
          multitask.add(register(username, password, media))
          username, password, media = None, None, None		
        username = argv[i+1]
      elif argv[i] == '-p':
        password = argv[i+1]
      elif argv[i] == '-m':
        media = argv[i+1]
      elif argv[i] == '-i':
        global ip
        ip = argv[i+1]
      i += 2		
    multitask.add(register(username, password, media))
    multitask.run()
  except KeyboardInterrupt:
    pass

    
