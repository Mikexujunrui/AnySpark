// README 效果图截图脚本（S262）——puppeteer 驱动前端创作台逐视图截图。
// 前置：后端 8000 + 前端 dev（5173/5174）已起，演示数据已灌（scripts/readme_demo.py）。
// 用法：NODE_PATH=$(npm root -g) node scripts/readme_shots.js [baseUrl] [outDir]
// 依赖全局 puppeteer（npm i -g puppeteer）；WebGL 图谱走 swiftshader 软渲染。
const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');

const BASE = process.argv[2] || 'http://localhost:5174';
const OUT = process.argv[3] || path.join(__dirname, '..', 'docs', 'assets', 'screenshots');
const BOOK = '雾城夜雨';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 按可见文本点击（取文本匹配的最深元素，避免点到外层容器）
async function clickText(page, text, { includes = false, timeout = 8000 } = {}) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    const ok = await page.evaluate(
      (t, inc) => {
        const els = [...document.querySelectorAll('button, [role="button"], a, div, span, li, h3, h4')];
        const hits = els.filter((e) => {
          const s = (e.textContent || '').trim();
          return inc ? s.includes(t) : s === t;
        });
        if (!hits.length) return false;
        // 最深（文本最短）优先；可见性过滤
        hits.sort((a, b) => (a.textContent || '').length - (b.textContent || '').length);
        const el = hits.find((e) => e.offsetParent !== null) || hits[0];
        el.click();
        return true;
      },
      text,
      includes
    );
    if (ok) return true;
    await sleep(400);
  }
  console.warn(`  ! clickText 未命中: ${text}`);
  return false;
}

async function shot(page, name) {
  const file = path.join(OUT, name);
  await page.screenshot({ path: file });
  console.log(`  ✓ ${name} (${(fs.statSync(file).size / 1024).toFixed(0)} KB)`);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--enable-unsafe-swiftshader', '--use-angle=swiftshader', '--lang=zh-CN'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 1000, deviceScaleFactor: 1.5 });

  // 1) 书架
  await page.goto(BASE + '/', { waitUntil: 'networkidle2', timeout: 60000 });
  await sleep(2500);
  await shot(page, '01-bookshelf.png');

  // 2) 对话写作（默认 tab；滚到底看工具链+总结）
  await page.goto(BASE + '/book/' + encodeURIComponent(BOOK), { waitUntil: 'networkidle2', timeout: 60000 });
  await sleep(3500);
  await clickText(page, '对话');
  await sleep(2000);
  await page.evaluate(() => {
    const boxes = [...document.querySelectorAll('div.overflow-y-auto')];
    const b = boxes.sort((x, y) => y.scrollHeight - x.scrollHeight)[0];
    if (b) b.scrollTop = b.scrollHeight;
  });
  await sleep(800);
  await shot(page, '02-chat.png');

  // 3) 章节编辑（选中第三章）
  await clickText(page, '章节');
  await sleep(1500);
  await clickText(page, '第三章 旧档案', { includes: true });
  await sleep(1800);
  await shot(page, '03-chapters.png');

  // 4) 知识图谱（知识库 → 图谱视图，等力导布局稳定）
  await clickText(page, '知识库');
  await sleep(1500);
  await clickText(page, '图谱');
  await sleep(5000);
  await clickText(page, '重置'); // 重置布局：力导重新居中收敛
  await sleep(3000);
  await shot(page, '04-graph.png');

  // 5) 伏笔面板
  await clickText(page, '伏笔');
  await sleep(1800);
  await shot(page, '05-foreshadow.png');

  // 6) 工作流画布（打开拆书提炼模板）
  await clickText(page, '工作流');
  await sleep(1800);
  await clickText(page, '拆书提炼', { includes: true });
  await sleep(2500);
  await page.click('[title="适配视图（全部节点可见）"]').catch(() => {});
  await sleep(1200);
  await shot(page, '06-workflow.png');

  // 7) 技巧面板（拆书产出的 skill 草稿）
  await clickText(page, '技巧');
  await sleep(1800);
  await shot(page, '07-skills.png');

  // 8) 人物关系网
  await clickText(page, '人物');
  await sleep(1500);
  await clickText(page, '关系网', { includes: true });
  await sleep(5000);
  await shot(page, '08-characters.png');

  await browser.close();
  console.log('done →', OUT);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});