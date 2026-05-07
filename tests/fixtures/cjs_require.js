const { loadFoundation, validateConfig } = require('./foundation');
const utils = require('./utils');
const helper = require('./helpers').helperFn;

function runDispatch() {
  const cfg = loadFoundation({});
  validateConfig(cfg);
  utils.log('go');
  helper();
}

module.exports = { runDispatch };
