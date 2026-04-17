module "network" {
  source = "./modules/network"
  cidr   = var.cidr
  name   = "main"
  providers = {
    aws = aws.main
  }
  depends_on = [module.vpc]
}

module "remote" {
  source  = "hashicorp/consul/aws"
  version = "0.1.0"
}

module "interpolated" {
  source = "${var.module_path}/network"
}

module "no_source" {
  name = "orphan"
}
