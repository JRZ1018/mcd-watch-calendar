// Deterministic vector layouts for the project's own social sharing assets.
// Usage: node promotion/render-assets.cjs [path-to-sharp-package]
const fs = require('node:fs');
const path = require('node:path');
const sharp = require(process.argv[2] || 'sharp');
const out = path.join(__dirname, 'xiaohongshu');
fs.mkdirSync(out, {recursive:true});
const P='#f6f4ed', K='#20231e', Y='#ffda35', M='#69705f';
const esc=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const text=(x,y,s,size=40,color=K,weight=400)=>`<text x="${x}" y="${y}" font-size="${size}" fill="${color}" font-weight="${weight}">${esc(s)}</text>`;
const rect=(x,y,w,h,fill,stroke='none')=>`<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${fill}" stroke="${stroke}" stroke-width="2"/>`;
const line=(x1,y1,x2,y2,color)=>`<path d="M${x1} ${y1}H${x2}" stroke="${color}" stroke-width="2"/>`;
function base(body,bg=P,w=1080,h=1440){return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><style>text{font-family:'Microsoft YaHei','Noto Sans CJK SC',sans-serif}</style>${rect(0,0,w,h,bg)}${body}</svg>`;}
function footer(dark=false){const c=dark?'#c3c9b8':M;return line(72,1240,1008,1240,c)+text(72,1293,'麦麦不忘 · 独立参赛作品 · 非麦当劳官方产品',25,c)+text(72,1338,'AI 辅助排版｜功能说明图，非手机日历实拍',22,c);}
const cards=[
  base(text(72,100,'MCD WATCH / 麦麦不忘',28,M)+
    text(72,270,'把麦当劳活动',88,K,700)+text(72,390,'放进你的日历。',88,K,700)+
    rect(72,445,680,18,Y)+text(72,535,'早餐 / 咖啡 / 联名周边',42,K)+
    rect(72,625,936,485,Y)+text(112,701,'选择主题，再复制订阅地址。',36,K,700)+
    rect(112,760,270,220,P)+rect(405,760,270,220,P)+rect(698,760,270,220,P)+
    text(140,815,'01',25,M)+text(140,900,'早餐',56,K,700)+
    text(433,815,'02',25,M)+text(433,900,'咖啡',56,K,700)+
    text(726,815,'03',25,M)+text(726,900,'联名周边',43,K,700)+
    text(112,1050,'直接使用公开日历，无需自己配置 MCP',29,K)+
    text(72,1185,'少记一件事，把时间留给生活。',31,M)+footer()),
  base(text(72,100,'01 / CHOOSE & COPY',28,Y)+
    text(72,270,'喜欢哪一类，',88,P,700)+text(72,390,'就订阅哪一类。',88,P,700)+
    text(72,515,'在网页上选一个主题',36,'#c3c9b8')+
    rect(72,580,210,86,Y)+text(123,638,'早餐',34,K,700)+
    rect(304,580,210,86,K,'#8e9584')+text(355,638,'咖啡',34,P)+
    rect(536,580,320,86,K,'#8e9584')+text(581,638,'联名周边',34,P)+
    rect(72,735,936,290,P)+text(112,807,'当前订阅范围：早餐',32,K)+
    rect(112,850,420,100,K)+text(152,916,'复制订阅地址',39,P)+
    `<path d="M605 890l0 92 25-22 22 40 22-12-22-40 33-3z" fill="${Y}" stroke="${K}" stroke-width="3"/>`+
    text(72,1120,'主题切换，也会切换对应的订阅源。',32,P)+
    text(72,1180,'搜索和日期开关仅影响网页列表。',27,'#c3c9b8')+footer(true),K),
  base(text(72,100,'02 / ADD TO YOUR CALENDAR',28,M)+
    text(72,270,'在你常用的',88,K,700)+text(72,390,'日历里添加。',88,K,700)+
    text(72,500,'选择支持 ICS 订阅的日历客户端',35,M)+
    rect(72,570,936,135,'#e9ebdf')+text(110,622,'01',25,M)+text(190,650,'找到「添加订阅日历」入口',36,K,700)+
    rect(72,730,936,135,Y)+text(110,782,'02',25,K)+text(190,810,'粘贴 HTTPS 订阅地址',36,K,700)+
    rect(72,890,936,135,'#e9ebdf')+text(110,942,'03',25,M)+text(190,970,'按需设置提醒与刷新偏好',36,K,700)+
    text(72,1100,'每六小时尝试更新，客户端刷新可能延迟。',29,K)+
    text(72,1150,'记录官方展示日期，不推断开售或截止日期。',27,M)+
    text(72,1198,'具体入口名称以日历客户端为准。',24,M)+footer())
];
(async()=>{
  for(let i=0;i<cards.length;i++){
    const stem=path.join(out,`${String(i+1).padStart(2,'0')}-${['cover','choose-topic','add-calendar'][i]}`);
    fs.writeFileSync(stem+'.svg',cards[i]);
    await sharp(Buffer.from(cards[i])).jpeg({quality:94,chromaSubsampling:'4:4:4'}).toFile(stem+'.jpg');
  }
  const preview=base(text(64,88,'MCD WATCH / 麦麦不忘',24,M)+text(64,245,'把好日子，',77,K,700)+text(64,345,'记下来。',77,K,700)+rect(64,376,355,14,Y)+text(64,455,'早餐 · 咖啡 · 联名周边',31,K)+text(64,518,'把官方活动日历变成可订阅的 ICS',25,M)+rect(844,76,292,432,Y)+text(880,147,'CALENDAR',22,K)+text(879,340,'ICS',86,K,700)+text(880,430,'选择主题，直接订阅',21,K)+text(64,592,'独立参赛作品 · 非麦当劳官方产品',20,M),P,1200,630);
  fs.mkdirSync(path.join(__dirname,'../docs/assets'),{recursive:true});
  await sharp(Buffer.from(preview)).png().toFile(path.join(__dirname,'../docs/assets/share-preview.png'));
  console.log('Rendered 3 portrait cards and the website sharing preview.');
})().catch(e=>{console.error(e.message);process.exitCode=1;});
