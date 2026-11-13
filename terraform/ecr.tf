# Private registry for demo-app images. Jenkins pushes <short-sha> tags and
# moves "latest-stable" (production) / "staging-stable" to the last image that
# passed its health check. rollback.sh pulls those tags.

resource "aws_ecr_repository" "demo_app" {
  name = var.ecr_repository_name

  # Tags must be movable, because latest-stable is re-pointed after every good deploy.
  image_tag_mutability = "MUTABLE"

  # Lets `terraform destroy` delete the repository even when it still holds images.
  force_delete = true

  # Free basic scan on every push, in addition to the Trivy gate in Jenkins.
  image_scanning_configuration {
    scan_on_push = true
  }
}

# Keep the newest images, but never expire the ones rollback depends on.
# An image matched by a higher-priority rule is not touched by lower ones,
# so rules 1 and 2 protect the stable images from rule 3.
resource "aws_ecr_lifecycle_policy" "demo_app" {
  repository = aws_ecr_repository.demo_app.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep the production rollback target"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["latest-stable"]
          countType     = "imageCountMoreThan"
          countNumber   = 1
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep the staging rollback target"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["staging-stable"]
          countType     = "imageCountMoreThan"
          countNumber   = 1
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 3
        description  = "Keep only the last ${var.ecr_keep_images} images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = var.ecr_keep_images
        }
        action = { type = "expire" }
      },
    ]
  })
}
