#!/usr/bin/env node
/**
 * 每日研报观点提炼 - 入口脚本
 * 用法: node run.mjs [--date YYYY-MM-DD]
 */

import { getToday } from './utils.mjs';

// 解析命令行参数
const args = process.argv.slice(2);
let date = getToday();

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--date' && i + 1 < args.length) {
    date = args[i + 1];
    break;
  }
}

// 执行主逻辑
import('./main.mjs').then(({ main }) => {
  main(date).catch(console.error);
});
