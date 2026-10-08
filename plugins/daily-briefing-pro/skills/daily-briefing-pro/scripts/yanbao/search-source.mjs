#!/usr/bin/env node
/**
 * 研报数据来源封装
 */

import { searchYanbaoke } from './yanbaoke-source.mjs';
import { searchIMA } from './ima-source.mjs';
import { searchWeb } from './web-source.mjs';

export async function searchReports(source, date) {
  switch (source) {
    case 'yanbaoke':
      return searchYanbaoke(date);
    case 'ima':
      return searchIMA(date);
    case 'web':
      return searchWeb(date);
    default:
      throw new Error(`Unknown source: ${source}`);
  }
}
