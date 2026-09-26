import {chromium} from 'playwright';
import {spawn} from 'child_process';
const FF=process.env.FF||'ffmpeg';
const FPS=30,DUR=60,N=FPS*DUR;
const ff=spawn(FF,['-y','-loglevel','error','-f','image2pipe','-framerate',String(FPS),'-c:v','mjpeg','-i','-','-i','music.wav','-c:v','libx264','-preset','slow','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-shortest','-movflags','+faststart','simplify-med-pitch.mp4'],{stdio:['pipe','inherit','inherit']});
const b=await chromium.launch();const p=await b.newPage({viewport:{width:1920,height:1080}});
p.on('pageerror',e=>console.log('ERR',e.message));
await p.goto('file://'+process.cwd()+'/pitch.html');await p.evaluate(()=>document.fonts.ready);
for(let i=0;i<N;i++){await p.evaluate(t=>render(t),i/FPS);const buf=await p.screenshot({type:'jpeg',quality:95});
 if(!ff.stdin.write(buf))await new Promise(r=>ff.stdin.once('drain',r)); if(i%300===0)console.log('frame',i);}
ff.stdin.end();await new Promise(r=>ff.on('close',r));await b.close();console.log('done');
