#!/usr/bin/env node
/**
 * daily-briefing-research-summary: 每日研报观点提炼
 * 整合研报客、IMA订阅、网络搜索三个来源，只取当天数据
 * 输出标准化表格格式
 */

import { searchReports } from './search-source.mjs';
import { formatDailySummary } from './format.mjs';
import { getToday } from './utils.mjs';

export async function main(date) {
  const today = date || getToday();
  
  console.log(`\n📊 每日研报观点提炼 (${today})\n`);
  console.log('正在从三个来源获取当天研报...\n');
  
  // 来源1: 研报客 - 只取当天
  console.log('🔍 来源1: 研报客...');
  const yanbaokeReports = await searchReports('yanbaoke', today);
  console.log(`   找到 ${yanbaokeReports.length} 份报告`);
  
  // 来源2: IMA订阅知识库 - 只取当天
  console.log('🔍 来源2: IMA订阅知识库...');
  const imaReports = await searchReports('ima', today);
  console.log(`   找到 ${imaReports.length} 份报告`);
  
  // 来源3: 网络搜索 - 只取当天
  console.log('🔍 来源3: 网络搜索...');
  const webReports = await searchReports('web', today);
  console.log(`   找到 ${webReports.length} 份报告`);
  
  // 合并所有报告
  const allReports = [...yanbaokeReports, ...imaReports, ...webReports];
  console.log(`\n📋 总计: ${allReports.length} 份当天研报\n`);
  
  if (allReports.length === 0) {
    console.log('⚠️ 当天暂无新增研报');
    return;
  }
  
  // 格式化输出
  const output = formatDailySummary(allReports, today);
  console.log(output);
  
  // 输出到文件（可选）
  // const fs = await import('fs');
  // fs.writeFileSync(`每日研报观点_${today.replace(/-/g, '')}.md`, output);
}

// 兼容直接运行
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(console.error);
}
