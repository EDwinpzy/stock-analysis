#!/usr/bin/env node
/**
 * 格式化输出 - V5
 * V4→V5修复：
 * 1. 板块分类优化：标题优先匹配，标题中的个股名决定板块而非内容中偶然提及的关键词
 * 2. 嘉元科技→铜箔（不再误分到光通信）
 * 3. 中金公司"本周精选"→策略（不再误分到光通信）
 * 4. 一德期货铜半年报→铜（不再误分到AI算力）
 * 5. 华西纺服→纺服（不再误分到AI算力）
 * 6. 标的提取：标题中的明确标的优先，内容中偶然提及的标的降权
 * 7. 观点提炼：提取不到有效观点时，用标题关键词生成简短描述
 * 8. 利好利空：策略/宏观类研报默认中性，不做利空判断
 */

// ========== A股标的精准提取 ==========
const STOCK_DICT = {
  '中际旭创': '300308', '新易盛': '300502', '天孚通信': '300394',
  '光迅科技': '002281', '华工科技': '000988', '特发信息': '000070',
  '烽火通信': '600498', '亨通光电': '600487', '中天科技': '600522',
  '诺德股份': '600110', '风华高科': '000636', '扬杰科技': '300373',
  '士兰微': '600460', '兆易创新': '603986', '北方华创': '002371',
  '雅克科技': '002409', '浪潮信息': '000977', '中科曙光': '603019',
  '斯达半导': '603290', '三环集团': '300408', '顺络电子': '002138',
  '嘉元科技': '688388', '永和股份': '605020', '多氟多': '002407',
  '天赐材料': '002709', '新宙邦': '300037', '永太科技': '002326',
  '牧原股份': '002714', '温氏股份': '300498', '金风科技': '002202',
  '东方电缆': '603606', '力量钻石': '301071', '杰普特': '688025',
  '特锐德': '300001', '并行科技': '920493', '巨化股份': '600160',
  '百隆东方': '601339', '兴业科技': '603928', '开润股份': '300577',
  '富春染织': '605189',
};
const CODE_TO_NAME = {};
for (const [n, c] of Object.entries(STOCK_DICT)) CODE_TO_NAME[c] = n;

// 券商/期货公司名单（排除作为标的）
const BROKER_NAMES = new Set([
  '华泰证券', '中信证券', '国泰君安', '招商证券', '东方财富',
  '浙商证券', '中金公司', '华源证券', '华西证券', '中国银河',
  '海通国际', '一德期货', '国信证券', '申万宏源', '银河证券',
  '东吴证券', '长江证券', '广发证券', '光大证券', '安信证券',
  '天风证券', '中泰证券', '华安证券', '东兴证券', '财通证券',
  '国盛证券', '兴业证券', '方正证券', '平安证券', '华创证券',
  '长安投研',
]);
const BROKER_CODES = new Set([
  '600030', '601688', '601211', '600999', '300059',
  '601788', '600837', '000776', '601377', '600109',
  '002736', '600918', '601198', '601162',
]);

// 个股→板块映射（标题中的个股名决定板块）
const STOCK_TO_SECTOR = {
  '嘉元科技': '铜箔', '诺德股份': '铜箔',
  '中际旭创': '光通信', '新易盛': '光通信', '天孚通信': '光通信',
  '光迅科技': '光通信', '华工科技': '光通信', '特发信息': '光通信',
  '烽火通信': '光通信', '亨通光电': '光通信', '中天科技': '光通信',
  '扬杰科技': '功率半导体', '士兰微': '功率半导体', '斯达半导': '功率半导体',
  '兆易创新': '半导体', '北方华创': '半导体', '雅克科技': '半导体',
  '并行科技': 'AI算力', '浪潮信息': 'AI算力', '中科曙光': 'AI算力',
  '特锐德': 'AI算力',
  '风华高科': '被动元件', '三环集团': '被动元件', '顺络电子': '被动元件',
  '永和股份': '氟化工', '多氟多': '氟化工', '天赐材料': '氟化工',
  '新宙邦': '氟化工', '永太科技': '氟化工', '巨化股份': '氟化工',
  '牧原股份': '养殖', '温氏股份': '养殖',
  '金风科技': '风电', '东方电缆': '风电',
  '力量钻石': '金刚石',
  '杰普特': '半导体',
  '百隆东方': '纺服', '兴业科技': '纺服', '开润股份': '纺服', '富春染织': '纺服',
};

export function formatDailySummary(reports, date) {
  if (!reports || reports.length === 0) return `\n⚠️ ${date} 暂无新增研报\n`;
  
  // 预处理
  const processed = reports.map(preProcess).filter(r => r !== null);
  
  // 去重
  const seen = new Set();
  const unique = processed.filter(r => {
    const key = r.titleClean.slice(0, 30);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  
  let output = `\n## 📊 每日研报观点提炼（${date}）\n\n`;
  
  const sectors = groupBySector(unique);
  const sectorOrder = ['光通信', '功率半导体', '半导体', '存储', 'AI算力',
    '铜箔', '被动元件', '氟化工', '新能源', '风电', '养殖', '券商',
    '金刚石', '纺服', '铜', '策略', '宏观', '其他'];
  
  // ==========================================
  // 核心逻辑：按板块聚合多券商观点
  // ==========================================
  output += `### 🔥 核心逻辑\n\n`;
  
  for (const sName of sectorOrder) {
    const sReports = sectors[sName];
    if (!sReports || sReports.length === 0) continue;
    
    // 板块方向：取多数方向
    const dirCounts = { '🔴利好': 0, '🟢利空': 0, '🟡中性': 0 };
    for (const r of sReports) dirCounts[getDirection(r)]++;
    const sectorDir = dirCounts['🟢利空'] > dirCounts['🔴利好'] ? '🟢利空' :
                      dirCounts['🟡中性'] > dirCounts['🔴利好'] ? '🟡中性' : '🔴利好';
    
    // 合并该板块所有标的（去重，过滤跨板块标的）
    const allStocks = new Set();
    for (const r of sReports) {
      for (let s of r.parsedStocks.split(/[、,]/)) {
        s = s.trim();
        if (!s || s === '其他板块' || s.endsWith('板块')) continue;
        // 过滤：标的所属板块必须匹配当前板块
        const stockName = s.replace(/\(.*?\)$/, ''); // 去掉(代码)
        const stockSector = STOCK_TO_SECTOR[stockName];
        if (stockSector && stockSector !== sName) continue; // 跨板块标的排除
        allStocks.add(s);
      }
    }
    const stocksStr = (new Set(['策略', '宏观', '其他'])).has(sName) ? '-' :
      (allStocks.size > 0 ? [...allStocks].slice(0, 5).join('、') : '-');
    
    // 逐条列出每家券商观点
    output += `**${sName}** ${sectorDir}\n\n`;
    
    const orgSeen = new Set();
    for (const r of sReports) {
      if (orgSeen.has(r.orgClean)) continue;
      orgSeen.add(r.orgClean);
      const summary = extractSummary(r, 120);
      output += `- **${r.orgClean}**：${summary}\n`;
    }
    
    output += `\n  → **重点标的**：${stocksStr}\n\n`;
  }
  
  // ==========================================
  // 总结表（板块聚合）
  // ==========================================
  output += `### 📋 总结表\n\n`;
  output += `| 板块 | 方向 | 核心逻辑 | 重点标的 | 来源券商 |\n`;
  output += `|------|------|----------|----------|----------|\n`;
  
  for (const sName of sectorOrder) {
    const sReports = sectors[sName];
    if (!sReports || sReports.length === 0) continue;
    
    // 方向
    const dirCounts = { '🔴利好': 0, '🟢利空': 0, '🟡中性': 0 };
    for (const r of sReports) dirCounts[getDirection(r)]++;
    const sectorDir = dirCounts['🟢利空'] > dirCounts['🔴利好'] ? '🟢利空' :
                      dirCounts['🟡中性'] > dirCounts['🔴利好'] ? '🟡中性' : '🔴利好';
    
    // 合并标的（过滤跨板块标的）
    const allStocks = new Set();
    for (const r of sReports) {
      for (let s of r.parsedStocks.split(/[、,]/)) {
        s = s.trim();
        if (!s || s === '其他板块' || s.endsWith('板块')) continue;
        const stockName = s.replace(/\(.*?\)$/, '');
        const stockSector = STOCK_TO_SECTOR[stockName];
        if (stockSector && stockSector !== sName) continue;
        allStocks.add(s);
      }
    }
    const stocksStr = (new Set(['策略', '宏观', '其他'])).has(sName) ? '-' :
      (allStocks.size > 0 ? [...allStocks].slice(0, 5).join('、') : '-');
    
    // 合并券商名
    const orgs = [...new Set(sReports.map(r => r.orgClean))].slice(0, 4).join('、');
    
    // 合并核心逻辑（取每条研报观点的前30字拼接）
    const logicParts = [];
    const orgSeen2 = new Set();
    for (const r of sReports) {
      if (orgSeen2.has(r.orgClean)) continue;
      orgSeen2.add(r.orgClean);
      logicParts.push(extractSummary(r, 40));
      if (logicParts.length >= 3) break;
    }
    const logic = logicParts.join('；');
    
    output += `| **${sName}** | ${sectorDir} | ${logic} | ${stocksStr} | ${orgs} |\n`;
  }
  
  // ==========================================
  // 机构观点详细版
  // ==========================================
  output += `\n### 📋 机构观点详细版\n\n`;
  output += `| 来源 | 报告标题 | 核心观点 | 标的 | 方向 |\n`;
  output += `|------|---------|---------|------|------|\n`;
  
  for (const report of unique.slice(0, 30)) {
    output += `| ${report.orgClean} | ${report.titleClean.slice(0,40)} | ${extractSummary(report, 60)} | ${report.parsedStocks} | ${getDirection(report)} |\n`;
  }
  
  if (unique.length > 30) output += `\n... 共 ${unique.length} 条，显示前30条\n`;
  
  return output;
}

// ========== 预处理 ==========
function preProcess(report) {
  const r = { ...report };
  
  let title = r.title || '';
  title = title.replace(/^\d{4}-?\d{2}-?\d{2}[-_\s]*/, '');
  title = title.replace(/^深度报告[-_]\d{4}-?\d{2}-?\d{2}[-_]*/, '');
  title = title.replace(/_\d+页?_\d+kb$/i, '');
  title = title.replace(/_\d+页?_\d+kb$/i, '');
  title = title.replace(/_\d+mb$/i, '');
  title = title.replace(/_\d+kb$/i, '');
  title = title.replace(/_\d+页?$/i, '');
  r.titleClean = title.trim();
  
  // 过滤明显无关的报告
  const skipPatterns = ['安全检测', '风险评估方法研究', '在线旅游竞赛',
    'AI安全', '提示词注入', '安全风险评测', '网络安全'];
  for (const p of skipPatterns) {
    if (r.titleClean.includes(p)) return null;
  }
  
  // 提取机构名
  let org = r.org || '';
  if (!org || org === '未知机构' || org === 'null') {
    const m1 = title.match(/^([^\-_0-9][^\-_]{2,8}?(?:证券|期货|投研|研究))[-_]/);
    if (m1) org = m1[1];
    else {
      const m2 = title.match(/^([^\-_0-9][^\-_]{2,8}?(?:国际|研究院|研究所))[-_]/);
      if (m2) org = m2[1];
    }
  }
  r.orgClean = cleanOrgName(org || '未知');
  
  // 标的提取（标题优先）
  r.parsedStocks = extractStocksFromReport(r);
  
  // 板块分类（标题优先）
  r.sector = detectSectorName(r);
  
  return r;
}

// ========== 标的提取（标题优先策略） ==========
function extractStocksFromReport(report) {
  const titleStocks = new Set();  // 标题中明确提到的标的
  const title = report.title || '';
  const content = report.content || '';
  const sector = report.sector || '';
  
  // === 标题中的标的 ===
  
  // 1. "公司名-代码.SH/SZ-" 模式（个股深度研报标准格式）
  const codeInTitle = title.match(/[-_]([\u4e00-\u9fa5]{2,6})[-_](\d{6})\.(?:SH|SZ|BJ)[-_]/);
  if (codeInTitle) {
    const name = codeInTitle[1];
    const code = codeInTitle[2];
    if (!BROKER_CODES.has(code) && !BROKER_NAMES.has(name)) {
      titleStocks.add(`${name}(${code})`);
    }
  }
  // 仅代码模式
  const codeOnly = title.match(/[-_](\d{6})\.(?:SH|SZ|BJ)[-_]/);
  if (codeOnly && !codeInTitle) {
    const code = codeOnly[1];
    if (!BROKER_CODES.has(code)) {
      const name = CODE_TO_NAME[code];
      if (name) titleStocks.add(`${name}(${code})`);
    }
  }
  
  // 2. 标题中的公司名匹配词典
  for (const [name, code] of Object.entries(STOCK_DICT)) {
    if (BROKER_NAMES.has(name)) continue;
    if (titleStocks.has(`${name}(${code})`)) continue;
    if (title.includes(name)) titleStocks.add(`${name}(${code})`);
  }
  
  // === 关键决策：个股深度研报只取标题标的 ===
  // 判断是否个股深度研报：
  // 1. 标题含 "代码.SH/SZ-" 格式
  // 2. 标题含 个股名+深度报告/首次覆盖/买入等推荐词
  const isIndividualReport = codeInTitle || codeOnly ||
    /深度报告|首次覆盖|买入评级|增持评级|公司深度|个股跟踪/.test(title);
  
  // 个股名出现在标题开头（券商名-个股名-... 格式）
  if (!isIndividualReport) {
    for (const name of Object.keys(STOCK_TO_SECTOR)) {
      if (BROKER_NAMES.has(name)) continue;
      const pattern = new RegExp(`[-_]${name}[-_]`);
      if (pattern.test(title)) {
        // 标题中有个股名作为主语，也是个股研报
        titleStocks.add(`${name}(${STOCK_DICT[name]})`);
        break;
      }
    }
  }
  
  if (isIndividualReport && titleStocks.size > 0) {
    // 个股深度研报：只返回标题中的标的
    const result = [...titleStocks].slice(0, 4);
    return result.join('、');
  }
  
  // === 行业研报：可以补充内容中的标的（同板块优先） ===
  const contentStocks = new Set();
  for (const [name, code] of Object.entries(STOCK_DICT)) {
    if (BROKER_NAMES.has(name)) continue;
    if (titleStocks.has(`${name}(${code})`)) continue;
    // 优先取同板块的标的
    if (content.includes(name)) {
      if (STOCK_TO_SECTOR[name] === sector || !sector) {
        contentStocks.add(`${name}(${code})`);
      }
    }
  }
  
  // 内容中的A股代码（同板块优先）
  const codeMatches = content.matchAll(/\b(\d{6})\b/g);
  for (const m of codeMatches) {
    const code = m[1];
    if (BROKER_CODES.has(code)) continue;
    const name = CODE_TO_NAME[code];
    if (name && !titleStocks.has(`${name}(${code})`)) {
      if (STOCK_TO_SECTOR[name] === sector || !sector) {
        contentStocks.add(`${name}(${code})`);
      }
    }
  }
  
  // 合并：标题标的优先，内容同板块标的最多补充2个
  const result = [...titleStocks, ...contentStocks].slice(0, 4);
  return result.length > 0 ? result.join('、') : (sector || '其他') + '板块';
}

// ========== 板块分类（标题优先策略） ==========
function detectSectorName(report) {
  const title = report.title || '';
  const content = report.content || '';
  
  // === 第一步：策略/宏观/精选类判断（最高优先级） ===
  // "本周精选"、"策略周报"等综合类研报不应分到具体行业
  if (/本周精选|策略周报|策略月报|配置建议|金股/.test(title)) return '策略';
  if (/ESG|央国企/.test(title)) return '策略';
  if (/医疗健康/.test(title) && /精选/.test(title)) return '策略';
  if (/宏观|经济|货币|利率|债市|通胀|宏观专题/.test(title)) return '宏观';
  
  // === 第二步：标题中的个股名直接决定板块 ===
  for (const [name, sector] of Object.entries(STOCK_TO_SECTOR)) {
    if (title.includes(name)) return sector;
  }
  
  // === 第二步：标题关键词匹配（高优先级） ===
  const titleSectorRules = [
    { name: '光通信', keywords: ['光模块', '光通信', '光纤光缆', '光芯片', '光互联', '光器件', 'MPO', 'CPO', 'NPO'] },
    { name: '功率半导体', keywords: ['功率半导体', '功率器件', 'SiC', 'GaN', 'IGBT', 'MOSFET'] },
    { name: '铜箔', keywords: ['铜箔', 'HVLP', '锂电铜箔', '极薄铜箔', '电解铜箔'] },
    { name: '存储', keywords: ['存储芯片', 'DRAM', 'NAND', 'HBM'] },
    { name: '氟化工', keywords: ['氟化工', '制冷剂', '含氟', '氢氟酸', '电子级氢氟酸'] },
    { name: '纺服', keywords: ['纺服', '服装', 'NIKE', '纺织', '服饰'] },
    { name: '铜', keywords: ['铜价', '铜矿', '电解铜', '美232', '铜半年报', '铜年报', '铜_'] },
    { name: '风电', keywords: ['风电', '海上风电', '风机'] },
    { name: '养殖', keywords: ['养殖', '猪周期', '畜牧'] },
    { name: '金刚石', keywords: ['金刚石', '培育钻'] },
    { name: '被动元件', keywords: ['MLCC', '被动元件', '电容', '电阻'] },
    { name: '半导体', keywords: ['半导体', '芯片', '国产替代', '前驱体', '光刻'] },
    { name: 'AI算力', keywords: ['算力租赁', 'AIDC', '算电岛', '超算云'] },
    { name: '新能源', keywords: ['新能源车', '光伏', '储能', '碳酸锂'] },
    { name: '券商', keywords: ['券商板块', '非银金融'] },
  ];
  for (const rule of titleSectorRules) {
    for (const kw of rule.keywords) {
      if (title.includes(kw)) return rule.name;
    }
  }
  
  // === 第三步：内容关键词匹配（低优先级，仅补充） ===
  const contentSectorRules = [
    { name: '光通信', keywords: ['光模块', '光通信', '光纤', '光芯片'] },
    { name: '功率半导体', keywords: ['功率半导体', '功率器件', 'SiC', 'GaN'] },
    { name: '铜箔', keywords: ['铜箔', 'HVLP', '锂电铜箔'] },
    { name: 'AI算力', keywords: ['人工智能', 'AI算力', '大模型'] },
    { name: '氟化工', keywords: ['氟化工', '制冷剂'] },
    { name: '存储', keywords: ['存储芯片', 'DRAM', 'NAND', 'HBM'] },
    { name: '被动元件', keywords: ['MLCC', '被动元件'] },
    { name: '半导体', keywords: ['半导体', '芯片', '国产替代'] },
  ];
  for (const rule of contentSectorRules) {
    for (const kw of rule.keywords) {
      if (content.includes(kw) && content.indexOf(kw) < content.length * 0.3) {
        // 只取内容前30%的关键词（避免尾部偶然提及）
        return rule.name;
      }
    }
  }
  
  // === 第四步：（策略/宏观已在第一步处理） ===
  
  return '其他';
}

// ========== 观点提炼 ==========
function extractSummary(report, maxLen = 80) {
  const content = report.content || '';
  const title = report.titleClean || '';
  
  if (!content || content.length < 30) return generateTitleSummary(title, maxLen);
  
  // 过滤免责声明
  const disclaimers = [
    '本人薪酬的任何部分', '免责声明', '重要声明', '请务必阅读',
    '证券研究报告', '本报告仅供', '投资者据此操作',
    '行业评级推荐', '公司评级推荐', '相对基准指数',
  ];
  
  // 优先找关键段落
  const keyPatterns = [
    /核心观点[：:\n]\s*([\s\S]{10,300}?)(?:\n\n|\n▶|\n■|$)/,
    /投资要点[：:\n]\s*([\s\S]{10,300}?)(?:\n\n|\n▶|\n■|$)/,
    /盈利预测[：:\n]\s*([\s\S]{10,300}?)(?:\n\n|\n▶|\n■|$)/,
    /投资建议[：:\n]\s*([\s\S]{10,300}?)(?:\n\n|\n▶|\n■|$)/,
    /主要观点[：:\n]\s*([\s\S]{10,300}?)(?:\n\n|\n▶|\n■|$)/,
  ];
  
  for (const pattern of keyPatterns) {
    const match = content.match(pattern);
    if (match && match[1].trim().length > 10) {
      const text = cleanText(match[1]);
      if (!disclaimers.some(d => text.includes(d))) {
        return truncate(text, maxLen);
      }
    }
  }
  
  // 次选：含信号词的句子
  const signalWords = ['看好', '推荐', '买入', '增持', '利好', '涨价', '景气', '增长', '紧缺', '放量', '超预期', '首推', '领军', '龙头'];
  const sentences = content.split(/[。\n]/).filter(s => s.trim().length > 15);
  for (const s of sentences) {
    const cleaned = cleanText(s.trim());
    if (disclaimers.some(d => cleaned.includes(d))) continue;
    for (const w of signalWords) {
      if (s.includes(w)) return truncate(cleaned, maxLen);
    }
  }
  
  // 兜底：从标题生成简短描述
  return generateTitleSummary(title, maxLen);
}

// 从标题生成简短观点描述
function generateTitleSummary(title, maxLen) {
  if (!title) return '详见报告';
  
  // 去掉券商名前缀
  let cleaned = title.replace(/^([^\-_]{2,10}?(?:证券|期货|国际|研究|投研))[-_]/, '');
  
  // 去掉股票代码
  cleaned = cleaned.replace(/[-_]\d{6}\.(?:SH|SZ|BJ)[-_]/, '-');
  
  // 去掉日期
  cleaned = cleaned.replace(/\d{4}-?\d{2}-?\d{2}/, '');
  
  // 去掉"深度报告"前缀
  cleaned = cleaned.replace(/^深度报告[-_]?/, '');
  
  return truncate(cleaned.trim() || title, maxLen);
}

// ========== 利好利空判断 ==========
function getDirection(report) {
  const title = report.title || '';
  const content = report.content || '';
  const text = title + ' ' + content;
  const sector = report.sector || '';
  
  // 策略/宏观类默认中性
  if (sector === '策略' || sector === '宏观') {
    if (/推荐|看好|利好|买入/.test(text)) return '🔴利好';
    if (/谨慎|风险|利空|下调/.test(text)) return '🟢利空';
    return '🟡中性';
  }
  
  // 过滤免责声明中的"风险"词（不算利空信号）
  const disclaimerPhrases = ['本人薪酬', '免责声明', '重要声明', '请务必阅读',
    '行业评级推荐', '相对基准指数'];
  let cleanText = text;
  for (const p of disclaimerPhrases) {
    // 去掉包含免责短语的整句
    cleanText = cleanText.replace(new RegExp(`[^。\n]*${p}[^。\n]*[。\n]?`, 'g'), '');
  }
  
  const bullish = ['看好', '利好', '推荐', '买入', '增持', '上调', '景气', '复苏',
    '增长', '放量', '紧缺', '涨价', '超预期', '加速', '金股', '首推', '强推',
    '领先', '领军', '龙头', '升级', '突破'];
  const bearish = ['谨慎', '利空', '减持', '下调', '回调', '下跌', '过剩',
    '放缓', '承压', '低于预期', '回落', '下滑', '控制弹性'];
  
  let bc = 0, bec = 0;
  for (const w of bullish) if (cleanText.includes(w)) bc++;
  for (const w of bearish) if (cleanText.includes(w)) bec++;
  
  // 标题明确推荐个股=利好
  if (/推荐|买入|增持|金股|首推/.test(title)) return '🔴利好';
  
  if (bec > bc + 2) return '🟢利空';
  if (bec > 0 && bc === 0) return '🟢利空';
  return '🔴利好';
}

// ========== 辅助函数 ==========
function cleanText(str) {
  return str.replace(/[\r\n\t]/g, ' ').replace(/\s+/g, ' ').replace(/[|]/g, '｜').trim();
}

function cleanOrgName(org) {
  if (!org || org === 'null') return '未知';
  return org.replace(/股份有限公司$/, '').replace(/有限公司$/, '').trim() || '未知';
}

function truncate(str, maxLen) {
  if (!str) return '';
  const s = str.trim();
  return s.length > maxLen ? s.slice(0, maxLen) + '...' : s;
}

function groupBySector(reports) {
  const sectors = {};
  for (const r of reports) {
    const s = r.sector || '其他';
    if (!sectors[s]) sectors[s] = [];
    sectors[s].push(r);
  }
  return sectors;
}
