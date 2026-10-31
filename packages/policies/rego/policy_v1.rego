# OPA policies (versioned). Embedded fallback evaluator mirrors this logic in packages/policies/src.
package hybridpay.v1

default decision := "DENY"

decision := "ALLOW" {
  input.amountMinor <= input.limits.perTxMinor
  input.dayTotalMinor + input.amountMinor <= input.limits.perDayMinor
  input.consentValid == true
  input.deviceRevoked == false
  input.kycOk == true
}

decision := "REVIEW" {
  not decision == "ALLOW"
  input.amountMinor <= input.limits.reviewCeilingMinor
  input.deviceRevoked == false
}

reason := "OK" { decision == "ALLOW" }
reason := "AMOUNT_OR_LIMIT" { decision == "REVIEW" }
reason := "FAIL_CLOSED" { decision == "DENY" }
