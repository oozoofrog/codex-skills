"use strict";

class AsyncQueue {
  constructor() {
    this.values = [];
    this.waiters = [];
    this.closed = false;
    this.failure = null;
  }

  push(value) {
    if (this.closed) return;
    const waiter = this.waiters.shift();
    if (waiter) waiter.resolve({ value, done: false });
    else this.values.push(value);
  }

  fail(error) {
    if (this.closed) return;
    this.failure = error;
    this.closed = true;
    for (const waiter of this.waiters.splice(0)) waiter.reject(error);
  }

  close() {
    if (this.closed) return;
    this.closed = true;
    for (const waiter of this.waiters.splice(0)) waiter.resolve({ value: undefined, done: true });
  }

  next() {
    if (this.values.length) return Promise.resolve({ value: this.values.shift(), done: false });
    if (this.failure) return Promise.reject(this.failure);
    if (this.closed) return Promise.resolve({ value: undefined, done: true });
    return new Promise((resolve, reject) => this.waiters.push({ resolve, reject }));
  }

  [Symbol.asyncIterator]() { return this; }
}

module.exports = { AsyncQueue };
