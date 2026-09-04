"use strict";

class AsyncQueue {
  constructor() {
    this.items = [];
    this.waiters = [];
    this.terminal = null;
  }

  push(value) {
    if (this.terminal) return;
    const waiter = this.waiters.shift();
    if (waiter) waiter.resolve({ value, done: false });
    else this.items.push(value);
  }

  end() {
    if (this.terminal) return;
    this.terminal = { done: true };
    for (const waiter of this.waiters.splice(0)) waiter.resolve({ value: undefined, done: true });
  }

  fail(error) {
    if (this.terminal) return;
    this.terminal = { error };
    for (const waiter of this.waiters.splice(0)) waiter.reject(error);
  }

  next() {
    if (this.items.length) return Promise.resolve({ value: this.items.shift(), done: false });
    if (this.terminal?.error) return Promise.reject(this.terminal.error);
    if (this.terminal) return Promise.resolve({ value: undefined, done: true });
    return new Promise((resolve, reject) => this.waiters.push({ resolve, reject }));
  }

  [Symbol.asyncIterator]() {
    return this;
  }
}

module.exports = { AsyncQueue };
