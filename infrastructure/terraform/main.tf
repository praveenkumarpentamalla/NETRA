# ──────────────────────────────────────────────────────────────
# Project NETRA — AWS Infrastructure (Terraform)
# Region: ap-south-1 (Mumbai) — data residency requirement
# ──────────────────────────────────────────────────────────────

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.27"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.12"
    }
  }

  backend "s3" {
    bucket         = "netra-terraform-state-mumbai"
    key            = "production/terraform.tfstate"
    region         = "ap-south-1"
    dynamodb_table = "netra-terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = "ap-south-1" # Mumbai — mandatory for data residency

  default_tags {
    tags = {
      Project     = "NETRA"
      Environment = "production"
      Compliance  = "DPDP-2023"
      DataClass   = "sensitive-biometric"
    }
  }
}

# ──────────────────────────────────────────────────────────────
# VPC — isolated network, no internet egress for data plane
# ──────────────────────────────────────────────────────────────

module "vpc" {
  source = "./modules/vpc"

  vpc_cidr             = "10.20.0.0/16"
  availability_zones   = ["ap-south-1a", "ap-south-1b", "ap-south-1c"]
  private_subnet_cidrs = ["10.20.1.0/24", "10.20.2.0/24", "10.20.3.0/24"]
  public_subnet_cidrs  = ["10.20.101.0/24", "10.20.102.0/24", "10.20.103.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = false # one NAT per AZ for HA

  enable_flow_logs    = true
  flow_log_retention  = 90
}

# ──────────────────────────────────────────────────────────────
# EKS Cluster
# ──────────────────────────────────────────────────────────────

module "eks" {
  source = "./modules/eks"

  cluster_name    = "netra-production"
  cluster_version = "1.29"

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnet_ids

  # Node groups
  node_groups = {
    general = {
      instance_types = ["m6i.xlarge"]
      min_size       = 3
      max_size       = 12
      desired_size   = 5
      disk_size      = 100
      labels         = { workload = "general" }
    }
    ai_gpu = {
      instance_types = ["g5.2xlarge"] # NVIDIA A10G for FR/ANPR/ReID inference
      min_size       = 2
      max_size       = 8
      desired_size   = 3
      disk_size      = 200
      labels         = { workload = "ai-inference" }
      taints = [{
        key    = "nvidia.com/gpu"
        value  = "true"
        effect = "NO_SCHEDULE"
      }]
    }
    streaming = {
      instance_types = ["c6i.2xlarge"] # CPU-optimised for WebRTC/transcoding
      min_size       = 2
      max_size       = 10
      desired_size   = 3
      disk_size      = 100
      labels         = { workload = "streaming" }
    }
  }

  # Encryption at rest for etcd secrets
  cluster_encryption_config = {
    provider_key_arn = module.kms.eks_secrets_key_arn
    resources        = ["secrets"]
  }

  enable_irsa = true # IAM Roles for Service Accounts

  cluster_endpoint_private_access = true
  cluster_endpoint_public_access  = false # private cluster — VPN/bastion only
}

# ──────────────────────────────────────────────────────────────
# RDS PostgreSQL (Multi-AZ, encrypted)
# ──────────────────────────────────────────────────────────────

module "rds" {
  source = "./modules/rds"

  identifier     = "netra-postgres-production"
  engine         = "postgres"
  engine_version = "16.2"
  instance_class = "db.r6g.2xlarge"

  allocated_storage     = 500
  max_allocated_storage = 2000
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id            = module.kms.rds_key_arn

  multi_az               = true
  backup_retention_period = 35
  backup_window           = "18:00-19:00" # UTC (23:30-00:30 IST, low traffic)

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnet_ids

  database_name = "netra_db"
  master_username = "netra_admin"
  # master_password sourced from Secrets Manager, not hardcoded

  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  performance_insights_enabled = true
  monitoring_interval          = 30

  deletion_protection = true
}

# ──────────────────────────────────────────────────────────────
# MSK (Managed Kafka)
# ──────────────────────────────────────────────────────────────

module "msk" {
  source = "./modules/msk"

  cluster_name           = "netra-kafka-production"
  kafka_version           = "3.6.0"
  number_of_broker_nodes  = 6 # 2 per AZ
  broker_instance_type    = "kafka.m5.2xlarge"
  broker_ebs_volume_size  = 1000

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnet_ids

  encryption_in_transit_client_broker = "TLS"
  encryption_at_rest_kms_key_arn      = module.kms.msk_key_arn

  client_authentication_sasl_scram = true

  enhanced_monitoring = "PER_TOPIC_PER_PARTITION"
}

# ──────────────────────────────────────────────────────────────
# S3 (MinIO replacement for production — or self-hosted MinIO on EKS)
# Using S3 with Object Lock for WORM audit storage
# ──────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "clips" {
  bucket = "netra-clips-production-mumbai"

  tags = { DataClass = "video-evidence" }
}

resource "aws_s3_bucket_versioning" "clips" {
  bucket = aws_s3_bucket.clips.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "clips" {
  bucket = aws_s3_bucket.clips.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = module.kms.s3_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "clips" {
  bucket = aws_s3_bucket.clips.id

  rule {
    id     = "tier-to-warm"
    status = "Enabled"
    transition {
      days          = 14
      storage_class = "STANDARD_IA"
    }
    transition {
      days          = 90
      storage_class = "GLACIER_IR"
    }
  }
}

# WORM-compliant audit log bucket
resource "aws_s3_bucket" "audit_logs" {
  bucket              = "netra-audit-worm-production-mumbai"
  object_lock_enabled = true

  tags = { DataClass = "audit-worm" }
}

resource "aws_s3_bucket_object_lock_configuration" "audit_logs" {
  bucket = aws_s3_bucket.audit_logs.id
  rule {
    default_retention {
      mode  = "COMPLIANCE"
      years = 7
    }
  }
}

# ──────────────────────────────────────────────────────────────
# KMS Keys
# ──────────────────────────────────────────────────────────────

module "kms" {
  source = "./modules/kms"

  keys = {
    eks_secrets = { description = "EKS etcd secrets encryption" }
    rds         = { description = "RDS PostgreSQL encryption" }
    msk         = { description = "MSK Kafka encryption" }
    s3          = { description = "S3 clip storage encryption" }
    camera_master = {
      description       = "Master key for per-camera DEK wrapping"
      enable_key_rotation = true
      rotation_period_days = 365
    }
    watchlist_master = {
      description = "Watchlist biometric template encryption — restricted access"
      # Separate policy: only Senior SP role + System Admin can use
    }
  }
}

# ──────────────────────────────────────────────────────────────
# WAF for ALB (PCR Console + API)
# ──────────────────────────────────────────────────────────────

resource "aws_wafv2_web_acl" "netra" {
  name  = "netra-waf-production"
  scope = "REGIONAL"

  default_action { allow {} }

  rule {
    name     = "RateLimitRule"
    priority = 1
    action { block {} }
    statement {
      rate_based_statement {
        limit              = 2000
        aggregate_key_type = "IP"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "RateLimitRule"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 2
    override_action { none {} }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "CommonRuleSet"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "SQLiRuleSet"
    priority = 3
    override_action { none {} }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesSQLiRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "SQLiRuleSet"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "netra-waf"
    sampled_requests_enabled   = true
  }
}

# ──────────────────────────────────────────────────────────────
# Outputs
# ──────────────────────────────────────────────────────────────

output "eks_cluster_endpoint" {
  value     = module.eks.cluster_endpoint
  sensitive = true
}

output "rds_endpoint" {
  value     = module.rds.endpoint
  sensitive = true
}

output "msk_bootstrap_brokers" {
  value     = module.msk.bootstrap_brokers_tls
  sensitive = true
}

output "clips_bucket_name" {
  value = aws_s3_bucket.clips.id
}
