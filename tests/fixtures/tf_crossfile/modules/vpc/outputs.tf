output "vpc_id" {
  value = aws_vpc.main.id
}

output "subnet_cidr" {
  value = aws_subnet.main.cidr_block
}
