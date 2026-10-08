#!/usr/bin/env node
/**
 * 工具函数
 */

export function getToday() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function getTodayShort() {
  const today = getToday();
  return today.replace(/-/g, '');
}
