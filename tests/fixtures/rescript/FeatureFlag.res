type flag = [
  | #DarkMode
  | #BetaCheckout
  | #NewLogger
]

let allFlags = [
  #DarkMode,
  #BetaCheckout,
  #NewLogger,
]

let flagToString = (flag: flag) =>
  switch flag {
  | #DarkMode => "DarkMode"
  | #BetaCheckout => "BetaCheckout"
  | #NewLogger => "NewLogger"
  }

let isEnabled = (config, flag) =>
  Belt.Array.some(config.flags, f => f === flag)

let isEnabledForUser = (user, flag) =>
  isEnabled(user.config, flag)

module Internal = {
  let parse = (json) => Json.decode(json)
}
