variable "function_name" {
  type = string
}

resource "aws_iam_role" "api" {
  name = "${var.function_name}-role"
}

resource "aws_lambda_function" "api" {
  function_name = var.function_name
  role          = aws_iam_role.api.arn
}

output "api_function_arn" {
  value = aws_lambda_function.api.arn
}
