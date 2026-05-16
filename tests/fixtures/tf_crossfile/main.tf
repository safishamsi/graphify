module "vpc" {
  source = "./modules/vpc"
  cidr   = "10.0.0.0/16"
  name   = "main"
}

resource "aws_subnet" "main" {
  vpc_id = module.vpc.vpc_id
  cidr   = module.vpc.subnet_cidr
}
