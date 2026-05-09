open FeatureFlag

let darkModeOn = (config) =>
  isEnabled(config, #DarkMode)

let betaForUser = (user) =>
  isEnabledForUser(user, #BetaCheckout)
