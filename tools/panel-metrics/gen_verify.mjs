// "Model state" Custom HTML 控件的离线验证外壳生成器。
// 预览面板里 iframe srcdoc 不跑脚本，所以把片段直接内联；每格给 id 加后缀，
// 渲染完用控件自带的 root.__msRender 喂一条假 push 数据（等价于宿主 postMessage）。
// 用法：node gen_verify.mjs <out.html> <WxH> <case,case,...> [片段路径]
//   case: screenshot|reading|generating|idle|queued|unloaded|error|stale
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const PRELUDE_STYLE = 'html,body{margin:0;height:100%;background:transparent;color:#eef2f6;font-family:Roboto,"Segoe UI",system-ui,sans-serif;overflow:hidden}';

const CASES = {
  screenshot: { state: 'reading', raw_state: 'reading', queued: 0, prompt_read: 101214, prompt_total: 167816, prompt_tokens: 101214 },
  reading: { state: 'reading', raw_state: 'reading', queued: 0, prompt_read: 8431, prompt_total: 104966, prompt_tokens: 8431 },
  generating: { state: 'generating', raw_state: 'generating', queued: 0, phase: 'writing a tool call: mcp__workspace__bash', generated: 1012, max_tokens: 32000, tok_s: 103.3 },
  idle: { state: 'idle', raw_state: 'idle', queued: 0, last_detail: 'last: 1,024 tokens at 103.4 tok/s' },
  queued: { state: 'generating', raw_state: 'generating', queued: 3, phase: 'thinking', generated: 512, max_tokens: 32000, tok_s: 96.1 },
  read_no_total: { state: 'reading', raw_state: 'reading', queued: 0, prompt_read: null, prompt_total: null, prompt_tokens: 24052 },
  gen_indet: { state: 'generating', raw_state: 'generating', queued: 0, phase: 'writing', generated: 210, max_tokens: 359945, tok_s: 111.4 },
  gen_est: { state: 'generating', raw_state: 'generating', queued: 0, phase: 'thinking', generated: 541, max_tokens: 359945, tok_s: 116.0, out_est: 1200 },
  unloaded: { state: 'unloaded', raw_state: 'unloaded', queued: 0 },
  error: { state: 'error', raw_state: 'error', queued: 0, last_detail: 'last: 12 tokens at – tok/s' },
  stale: null,
};

const [out, size, caseList, fragPath] = process.argv.slice(2);
const [W, H] = size.split('x').map(Number);
const names = caseList.split(',');
if (!names.every((n) => n in CASES)) throw new Error('unknown case');

// 片段默认取本文件同级的控件本体（本地 C:\work\phonebox\ 下那份同理）
const HERE = path.dirname(fileURLToPath(import.meta.url));
const base = fs.readFileSync(fragPath || path.join(HERE, 'strata_model_state_html_widget.html'), 'utf8');
const fragFor = (i) => base                                    // id 后缀化：markup 与 getElementById 同步
  .replace(/id="(ms(?:-\w+)?)"/g, (_, id) => `id="${id}${i}"`)
  .replace(/getElementById\("(ms(?:-\w+)?)"\)/g, (_, id) => `getElementById("${id}${i}")`);

const cells = names.map((n, i) => {
  return `<figure><figcaption>${n}${n === 'screenshot' ? ' (对照原图)' : ''} — ${W}×${H}</figcaption><div class="card">${fragFor(i)}</div></figure>`;
}).join('\n');

const DATA = JSON.stringify(names.map((n) => (CASES[n] ? { strata_state: { data: CASES[n], at: 0, expiresAt: 0 } } : {})));

const html = `<!doctype html><html><head><meta charset="utf-8"><title>${size} ${names.join(' ')}</title>
<style>
:root{color-scheme:dark;--bg:#06080b;--card:rgba(255,255,255,0.045);--line:rgba(255,255,255,0.08)}
*{box-sizing:border-box;margin:0}
${PRELUDE_STYLE.replace('html,body', 'body')}
body{background:var(--bg);padding:10px;display:flex;flex-direction:column;gap:12px;width:max-content;overflow:auto;height:auto}
figure{margin:0}
figcaption{color:#8a94a3;font-size:11px;margin:0 0 4px 2px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;overflow:hidden;width:${W}px;height:${H}px;position:relative;font-family:Roboto,"Segoe UI",system-ui,sans-serif;color:#eef2f6}
</style></head><body>
${cells}
<script>
var DATA = ${DATA};
document.querySelectorAll('.card > .ms').forEach(function (el, i) {
  if (el.__msRender) el.__msRender(DATA[i] && DATA[i].strata_state);
  var cap = el.closest('figure').querySelector('figcaption');
  var over = el.scrollHeight > el.clientHeight + 1 ? ' ⚠溢出' : '';
  cap.textContent += ' · 字号 ' + el.dataset.fs + 'px' + over;
});
<\/script></body></html>`;

fs.writeFileSync(out, html);
console.log('wrote', out, (html.length / 1024).toFixed(1) + 'KB;', size, names.join(','));
