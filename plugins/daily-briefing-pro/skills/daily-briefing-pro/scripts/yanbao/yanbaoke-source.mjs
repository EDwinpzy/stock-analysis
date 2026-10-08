#!/usr/bin/env node
/**
 * 研报客数据源 V2 - 修复日期参数名 + 扩大关键词覆盖
 */

const API_BASE = 'https://api.yanbaoke.cn/skills/search_report';
const VERSION = '2.1.0';
const SKILL_ID = 'yanbaoke-research-report-download';

export async function searchYanbaoke(date) {
  const reports = [];
  const keywords = [
    '人工智能', '半导体', '光模块', '新能源', '券商',
    '氟化工', '功率半导体', '储能', '光伏', '锂电',
    '风电', '养殖', '被动元件', '铜箔', '存储芯片',
    '金股', '策略', '深度报告'
  ];
  
  for (const keyword of keywords) {
    try {
      const params = new URLSearchParams({
        keyword,
        size: '20',
        search_type: 'title',
        startdate: date,    // 修复：startdate而非start_date
        enddate: date       // 修复：enddate而非end_date
      });
      
      const resp = await fetch(`${API_BASE}?${params}`, {
        headers: {
          'X-Skill-Version': VERSION,
          'X-Skill-ID': SKILL_ID,
        }
      });
      
      if (!resp.ok) continue;
      
      const data = await resp.json();
      
      if (data.success && data.data) {
        for (const item of data.data) {
          reports.push({
            source: '研报客',
            title: item.title,
            org: item.org_name || '未知机构',
            date: item.time || date,
            pages: item.pagenum || 0,
            content: item.content || '',
            url: item.url || '',
            type: item.rtype_name || '行业研究',
            stock: item.stock_name || ''
          });
        }
      }
    } catch (err) {
      console.warn(`研报客搜索失败 [${keyword}]: ${err.message}`);
    }
  }
  
  return reports;
}
