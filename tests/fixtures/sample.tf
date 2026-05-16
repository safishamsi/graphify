resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}

data "aws_ami" "ubuntu" {
  most_recent = true
}

module "network" {
  source = "./modules/network"
  cidr   = var.cidr
}

variable "region" {
  default = "us-east-1"
}

output "vpc_id" {
  value = module.network.vpc_id
}

locals {
  env = "prod"
}

provider "aws" {
  region = var.region
}
