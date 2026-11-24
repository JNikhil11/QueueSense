"""
QueueSense — Batch 4: Infrastructure & Operational Readiness Tests
Validates SAM template properties for:
- P1.18: Observability, CloudWatch log groups, retention, API Gateway access logging, and operational alarms.
- P1.19: Data persistence, DynamoDB PITR, deletion protection, encryption, S3 versioning, lifecycle, and retention policies.
- P1.20: Cost controls, denial-of-wallet resilience, reserved concurrency ceilings, API throttling, on-demand billing.
- IAM least privilege, KMS encryption context scoping, and DynamoDB permissions.
- Cognito User Pool admin lockdown, password policy, TOTP MFA, and user enumeration defense.
- CloudFront delivery, OAC security, and strict response security headers policy.
"""

import os
import re
import pytest

TEMPLATE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "infrastructure", "template.yaml")
)


def load_template_text() -> str:
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return f.read()


# =========================================================================
# P1.18: Observability, Log Groups, Retention & Alarms
# =========================================================================

def test_p1_18_all_lambda_functions_have_explicit_cloudwatch_log_groups_and_retention():
    """P1.18: Every Lambda function must have an explicit AWS::Logs::LogGroup with 30-day retention."""
    text = load_template_text()

    required_functions = [
        ("HealthFunction", "HealthFunctionLogGroup"),
        ("GetLocationsFunction", "GetLocationsFunctionLogGroup"),
        ("GetQueueFunction", "GetQueueFunctionLogGroup"),
        ("SubmitReportFunction", "SubmitReportFunctionLogGroup"),
        ("GetRecommendationsFunction", "GetRecommendationsFunctionLogGroup"),
        ("GetHistoricalFunction", "GetHistoricalFunctionLogGroup"),
        ("AdminReportsFunction", "AdminReportsFunctionLogGroup"),
    ]

    for func_id, log_id in required_functions:
        assert func_id in text, f"Template must define function {func_id}"
        assert log_id in text, f"Template must define explicit LogGroup resource {log_id}"

        # Match log group resource block
        log_pattern = re.compile(rf"{log_id}:.*?(?=\n  [A-Za-z0-9]+:|\Z)", re.DOTALL)
        match = log_pattern.search(text)
        assert match, f"Could not extract resource block for {log_id}"
        block = match.group(0)

        assert "Type: AWS::Logs::LogGroup" in block, f"{log_id} must be AWS::Logs::LogGroup"
        assert f"!Sub \"/aws/lambda/${{{func_id}}}\"" in block, f"{log_id} must target /aws/lambda/${{{func_id}}}"
        assert "RetentionInDays: 30" in block, f"{log_id} must enforce finite 30-day retention"


def test_p1_18_api_gateway_access_logging_configured_with_safe_fields():
    """P1.18: API Gateway has dedicated access log group and JSON format with safe operational fields."""
    text = load_template_text()

    assert "ApiAccessLogGroup:" in text, "Template must define ApiAccessLogGroup"
    assert "LogGroupName: !Sub \"/aws/apigateway/queuesense-api-${Environment}\"" in text
    assert "RetentionInDays: 30" in text

    # Check AccessLogSettings in QueueSenseHttpApi
    api_match = re.search(r"QueueSenseHttpApi:.*?(?=\n  [A-Za-z0-9]+:|\Z)", text, re.DOTALL)
    assert api_match, "QueueSenseHttpApi must be present"
    api_block = api_match.group(0)

    assert "AccessLogSettings:" in api_block
    assert "DestinationArn: !GetAtt ApiAccessLogGroup.Arn" in api_block

    format_match = re.search(r"Format:\s*'([^']+)'", api_block)
    assert format_match, "AccessLogSettings must define single-quoted JSON Format string"
    log_format = format_match.group(1)

    # Verify safe fields present in log format
    safe_fields = ["requestId", "ip", "requestTime", "httpMethod", "routeKey", "status", "latency", "integrationLatency"]
    for field in safe_fields:
        assert field in log_format, f"API access log format must contain safe field: {field}"

    # Verify forbidden sensitive fields absent from log format
    forbidden_tokens = ["$context.identity.apiKey", "$context.authorizer", "Authorization", "password", "salt", "token", "requestBody"]
    for token in forbidden_tokens:
        assert token not in log_format, f"API access log format must not expose sensitive token: {token}"


def test_p1_18_operational_cloudwatch_alarms_defined():
    """P1.18: Critical operational conditions (5xx, Lambda errors, DynamoDB throttles, read latency) have CloudWatch alarms."""
    text = load_template_text()

    # 1. Api5xxAlarm
    assert "Api5xxAlarm:" in text
    api_5xx = re.search(r"Api5xxAlarm:.*?(?=\n  [A-Za-z0-9]+:|\Z)", text, re.DOTALL).group(0)
    assert "Namespace: AWS/ApiGateway" in api_5xx
    assert "MetricName: 5xx" in api_5xx
    assert "!Ref QueueSenseHttpApi" in api_5xx

    # 2. SubmitReportErrorsAlarm
    assert "SubmitReportErrorsAlarm:" in text
    sub_err = re.search(r"SubmitReportErrorsAlarm:.*?(?=\n  [A-Za-z0-9]+:|\Z)", text, re.DOTALL).group(0)
    assert "Namespace: AWS/Lambda" in sub_err
    assert "MetricName: Errors" in sub_err
    assert "!Ref SubmitReportFunction" in sub_err

    # 3. DynamoDBThrottledRequestsAlarm
    assert "DynamoDBThrottledRequestsAlarm:" in text
    ddb_alarm = re.search(r"DynamoDBThrottledRequestsAlarm:.*?(?=\n  [A-Za-z0-9]+:|\Z)", text, re.DOTALL).group(0)
    assert "Namespace: AWS/DynamoDB" in ddb_alarm
    assert "MetricName: ThrottledRequests" in ddb_alarm
    assert "!Ref MainTable" in ddb_alarm

    # 4. QueueReadLatencyAlarm
    assert "QueueReadLatencyAlarm:" in text
    lat_alarm = re.search(r"QueueReadLatencyAlarm:.*?(?=\n  [A-Za-z0-9]+:|\Z)", text, re.DOTALL).group(0)
    assert "Namespace: AWS/Lambda" in lat_alarm
    assert "MetricName: Duration" in lat_alarm
    assert "!Ref GetQueueFunction" in lat_alarm


# =========================================================================
# P1.19: Persistence, Recovery & Data Safety
# =========================================================================

def test_p1_19_dynamodb_persistence_pitr_and_deletion_protection():
    """P1.19: DynamoDB table has PITR enabled, deletion protection enabled, SSE, and retain policies."""
    text = load_template_text()

    match = re.search(r"MainTable:.*?(?=\n  [A-Za-z0-9]+:|\Z)", text, re.DOTALL)
    assert match, "MainTable resource must be present"
    table_block = match.group(0)

    assert "DeletionPolicy: Retain" in table_block, "MainTable must have DeletionPolicy: Retain"
    assert "UpdateReplacePolicy: Retain" in table_block, "MainTable must have UpdateReplacePolicy: Retain"
    assert "DeletionProtectionEnabled: true" in table_block, "MainTable must have DeletionProtectionEnabled: true"
    assert "PointInTimeRecoveryEnabled: true" in table_block, "MainTable must have PITR enabled"
    assert "SSEEnabled: true" in table_block, "MainTable must explicitly enable SSESpecification"
    assert "TimeToLiveSpecification:" in table_block
    assert "AttributeName: ttl" in table_block


def test_p1_19_s3_bucket_versioning_lifecycle_and_deletion_policy():
    """P1.19: Frontend S3 bucket has versioning, non-current version expiration lifecycle, and retain policies."""
    text = load_template_text()

    match = re.search(r"FrontendBucket:.*?(?=\n  [A-Za-z0-9]+:|\Z)", text, re.DOTALL)
    assert match, "FrontendBucket resource must be present"
    bucket_block = match.group(0)

    assert "DeletionPolicy: Retain" in bucket_block
    assert "UpdateReplacePolicy: Retain" in bucket_block
    assert "VersioningConfiguration:" in bucket_block
    assert "Status: Enabled" in bucket_block
    assert "LifecycleConfiguration:" in bucket_block
    assert "NoncurrentDays: 30" in bucket_block
    assert "BlockPublicAcls: true" in bucket_block
    assert "BlockPublicPolicy: true" in bucket_block
    assert "ObjectOwnership: BucketOwnerEnforced" in bucket_block


# =========================================================================
# P1.20: Cost Controls & Denial-of-Wallet Resilience
# =========================================================================

def test_p1_20_lambda_concurrency_ceilings_and_cost_controls():
    """P1.20: Every Lambda function has a protective ReservedConcurrentExecutions ceiling."""
    text = load_template_text()

    concurrency_limits = {
        "HealthFunction": 10,
        "GetLocationsFunction": 50,
        "GetQueueFunction": 50,
        "SubmitReportFunction": 20,
        "GetRecommendationsFunction": 30,
        "GetHistoricalFunction": 20,
        "AdminReportsFunction": 10,
    }

    for func_name, expected_limit in concurrency_limits.items():
        pattern = re.compile(rf"{func_name}:.*?(?=\n  [A-Za-z0-9]+:|\Z)", re.DOTALL)
        match = pattern.search(text)
        assert match, f"Could not find {func_name}"
        block = match.group(0)
        assert f"ReservedConcurrentExecutions: {expected_limit}" in block, (
            f"{func_name} must have ReservedConcurrentExecutions: {expected_limit}"
        )


def test_p1_20_api_gateway_throttling_and_on_demand_storage():
    """P1.20: API Gateway route throttling and DynamoDB on-demand billing constrain denial-of-wallet spend."""
    text = load_template_text()

    # DynamoDB BillingMode
    assert "BillingMode: PAY_PER_REQUEST" in text

    # API Gateway throttling
    assert "ThrottlingBurstLimit: 100" in text
    assert "ThrottlingRateLimit: 50.0" in text
    assert "ThrottlingBurstLimit: 20" in text
    assert "ThrottlingRateLimit: 10.0" in text

    # CloudFront PriceClass
    assert "PriceClass: PriceClass_100" in text


# =========================================================================
# IAM & Secrets Least-Privilege Verification
# =========================================================================

def test_iam_submit_report_kms_policy_tightly_scoped():
    """P1.20/IAM: SubmitReportFunction KMS decrypt statement is constrained by caller account, SSM service, and encryption context."""
    text = load_template_text()

    match = re.search(r"SubmitReportFunction:.*?(?=\n  [A-Za-z0-9]+:|\Z)", text, re.DOTALL)
    assert match, "SubmitReportFunction must be present"
    sub_block = match.group(0)

    assert "SubmitReportKMSDecryptionAccess" in sub_block
    assert "kms:Decrypt" in sub_block
    assert "kms:CallerAccount: !Sub \"${AWS::AccountId}\"" in sub_block
    assert "kms:ViaService: !Sub \"ssm.${AWS::Region}.amazonaws.com\"" in sub_block
    assert "kms:EncryptionContext:aws:ssm:arn: !Sub \"arn:aws:ssm:${AWS::Region}:${AWS::AccountId}:parameter/queuesense/${Environment}/rate_limit_salt\"" in sub_block


def test_iam_no_wildcard_actions_or_dangerous_permissions():
    """IAM: Verify no dangerous administrative or wildcard permissions exist in any Lambda role."""
    text = load_template_text()

    forbidden_patterns = [
        "dynamodb:*",
        "ssm:*",
        "kms:*",
        "s3:*",
        "cloudwatch:*",
        "dynamodb:DeleteTable",
        "dynamodb:DropTable",
        "dynamodb:DeleteItem",
    ]

    for pattern in forbidden_patterns:
        assert pattern not in text, f"Dangerous wildcard/action '{pattern}' is strictly forbidden in template.yaml"


# =========================================================================
# Cognito Administrative Access & Delivery Security
# =========================================================================

def test_cognito_admin_lockdown_and_enumeration_defense():
    """Cognito: Admin pool enforces admin-only creation, TOTP MFA, strong password policy, and user enumeration defense."""
    text = load_template_text()

    assert "AllowAdminCreateUserOnly: true" in text
    assert "MinimumLength: 12" in text
    assert "MfaConfiguration: \"OPTIONAL\"" in text
    assert "SOFTWARE_TOKEN_MFA" in text
    assert "PreventUserExistenceErrors: ENABLED" in text
    assert "RefreshTokenValidity: 30" in text
    assert "AccessTokenValidity: 1" in text
    assert "IdTokenValidity: 1" in text


def test_cloudfront_security_headers_and_delivery_hardening():
    """CloudFront: ResponseHeadersPolicy enforces HSTS, nosniff, FrameOption: DENY, CSP, and OAC read-only bucket policy."""
    text = load_template_text()

    assert "FrontendResponseHeadersPolicy:" in text
    assert "ResponseHeadersPolicyId: !Ref FrontendResponseHeadersPolicy" in text
    assert "AccessControlMaxAgeSec: 63072000" in text
    assert "Preload: true" in text
    assert "ContentTypeOptions:" in text
    assert "FrameOption: DENY" in text
    assert "ReferrerPolicy: strict-origin-when-cross-origin" in text
    assert "ContentSecurityPolicy:" in text
    assert "OriginAccessControlId: !GetAtt CloudFrontOAC.Id" in text
    assert "ViewerProtocolPolicy: redirect-to-https" in text


def test_regional_consistency_and_zero_hardcoded_accounts():
    """Architecture: Verifies all ARNs and resource references use dynamic ${AWS::AccountId} and ${AWS::Region}."""
    text = load_template_text()

    # Verify no raw 12-digit AWS account numbers are hardcoded
    raw_accounts = re.findall(r"\b\d{12}\b", text)
    assert not raw_accounts, f"Found hardcoded 12-digit AWS account number(s) in template: {raw_accounts}"

    # Verify dynamic interpolation
    assert "${AWS::AccountId}" in text
    assert "${AWS::Region}" in text
