"""
QueueSense — Batch 4: Infrastructure & Operational Readiness Semantic Tests
Parses infrastructure/template.yaml into structured CloudFormation data structures using PyYAML.
Validates:
- P1.18: Observability, CloudWatch log groups, 30-day retention, privacy-preserving API access logging, and operational alarms with SNS wiring.
- P1.19: Data persistence, DynamoDB PITR, deletion protection, encryption, S3 versioning, lifecycle expiration, and retain policies.
- P1.20: Cost controls, denial-of-wallet resilience, reserved concurrency ceilings, API throttling, on-demand billing.
- IAM least privilege, KMS encryption context scoping, and DynamoDB permissions.
- Cognito User Pool admin lockdown, mandatory TOTP MFA ("ON"), password policy, and user enumeration defense.
- CloudFront SPA routing via CloudFront Function, elimination of global 403/404 rewrites, and strict response security headers.
"""

import os
import json
import re
import pytest
import yaml

TEMPLATE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "infrastructure", "template.yaml")
)


class CfnYamlLoader(yaml.SafeLoader):
    """Custom YAML loader supporting CloudFormation and SAM intrinsic tags."""
    pass


def _cfn_tag_constructor(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return {tag_suffix: loader.construct_scalar(node)}
    elif isinstance(node, yaml.SequenceNode):
        return {tag_suffix: loader.construct_sequence(node)}
    elif isinstance(node, yaml.MappingNode):
        return {tag_suffix: loader.construct_mapping(node)}


CfnYamlLoader.add_multi_constructor("!", _cfn_tag_constructor)


def load_cfn_template() -> dict:
    """Loads and returns the parsed CloudFormation template as structured data."""
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return yaml.load(f, Loader=CfnYamlLoader)


@pytest.fixture(scope="module")
def template():
    return load_cfn_template()


# =========================================================================
# P1.18: Observability, Log Groups, Retention & Alarms
# =========================================================================

def test_semantic_log_groups_and_retention(template):
    """P1.18: Every Lambda function has a dedicated AWS::Logs::LogGroup with finite 30-day retention."""
    resources = template.get("Resources", {})

    expected_functions = [
        "HealthFunction",
        "GetLocationsFunction",
        "GetQueueFunction",
        "SubmitReportFunction",
        "GetRecommendationsFunction",
        "GetHistoricalFunction",
        "AdminReportsFunction",
    ]

    for func_name in expected_functions:
        log_group_name = f"{func_name}LogGroup"
        assert log_group_name in resources, f"Log group resource {log_group_name} missing from template"
        log_res = resources[log_group_name]
        assert log_res.get("Type") == "AWS::Logs::LogGroup"

        props = log_res.get("Properties", {})
        assert props.get("RetentionInDays") == 30, (
            f"{log_group_name} must enforce RetentionInDays: 30"
        )
        assert props.get("LogGroupName") == {"Sub": f"/aws/lambda/${{{func_name}}}"}


def test_semantic_api_gateway_access_logging_privacy(template):
    """P1.18: API Gateway access logging uses structured JSON with safe operational fields, strictly excluding raw IP."""
    resources = template.get("Resources", {})

    # Check dedicated log group
    assert "ApiAccessLogGroup" in resources
    api_log_res = resources["ApiAccessLogGroup"]
    assert api_log_res.get("Type") == "AWS::Logs::LogGroup"
    assert api_log_res.get("Properties", {}).get("RetentionInDays") == 30

    # Check API Gateway AccessLogSettings
    http_api = resources.get("QueueSenseHttpApi", {})
    props = http_api.get("Properties", {})
    access_log_settings = props.get("AccessLogSettings", {})

    assert access_log_settings.get("DestinationArn") == {"GetAtt": "ApiAccessLogGroup.Arn"}

    format_str = access_log_settings.get("Format", "")
    assert format_str, "AccessLogSettings Format string is missing"

    # Parse Format string as JSON
    format_data = json.loads(format_str)

    # 1. Privacy assertion: Raw client IP MUST NOT be logged
    assert "ip" not in format_data, "Access log must NOT include raw IP address key ('ip')"
    assert "$context.identity.sourceIp" not in format_str, (
        "Access log format must strictly exclude $context.identity.sourceIp"
    )

    # 2. Operational assertions: Safe telemetry fields MUST be logged
    safe_expected_fields = [
        "requestId",
        "requestTime",
        "httpMethod",
        "routeKey",
        "status",
        "protocol",
        "responseLength",
        "latency",
        "integrationLatency",
        "integrationStatus",
    ]
    for field in safe_expected_fields:
        assert field in format_data, f"Access log format must include safe operational field: {field}"

    # 3. Security assertions: Credentials, authorization headers, or request bodies MUST NOT be logged
    forbidden_tokens = ["Authorization", "password", "salt", "token", "requestBody", "$context.authorizer"]
    for token in forbidden_tokens:
        assert token not in format_str, f"Access log format must not contain sensitive token: {token}"


def test_semantic_cloudwatch_alarms_and_sns_actions(template):
    """P1.18: CloudWatch alarms are configured with valid metric dimensions, thresholds, and wired to OperationalAlertsTopic."""
    resources = template.get("Resources", {})

    # Verify SNS Topic and optional Subscription
    assert "OperationalAlertsTopic" in resources
    assert resources["OperationalAlertsTopic"]["Type"] == "AWS::SNS::Topic"
    assert "OperationalAlertsSubscription" in resources
    sub = resources["OperationalAlertsSubscription"]
    assert sub.get("Type") == "AWS::SNS::Subscription"
    assert sub.get("Condition") == "HasAlarmEmail"

    alarm_specs = {
        "Api5xxAlarm": {
            "Namespace": "AWS/ApiGateway",
            "MetricName": "5xx",
            "Threshold": 5,
            "Statistic": "Sum",
            "DimensionName": "ApiId",
            "DimensionValue": {"Ref": "QueueSenseHttpApi"},
        },
        "SubmitReportErrorsAlarm": {
            "Namespace": "AWS/Lambda",
            "MetricName": "Errors",
            "Threshold": 3,
            "Statistic": "Sum",
            "DimensionName": "FunctionName",
            "DimensionValue": {"Ref": "SubmitReportFunction"},
        },
        "DynamoDBThrottledRequestsAlarm": {
            "Namespace": "AWS/DynamoDB",
            "MetricName": "ThrottledRequests",
            "Threshold": 1,
            "Statistic": "Sum",
            "DimensionName": "TableName",
            "DimensionValue": {"Ref": "MainTable"},
        },
        "QueueReadLatencyAlarm": {
            "Namespace": "AWS/Lambda",
            "MetricName": "Duration",
            "Threshold": 3000,
            "Statistic": "Average",
            "DimensionName": "FunctionName",
            "DimensionValue": {"Ref": "GetQueueFunction"},
        },
    }

    for alarm_id, spec in alarm_specs.items():
        assert alarm_id in resources, f"Alarm {alarm_id} missing from template"
        alarm = resources[alarm_id]
        assert alarm.get("Type") == "AWS::CloudWatch::Alarm"
        props = alarm.get("Properties", {})

        assert props.get("Namespace") == spec["Namespace"]
        assert props.get("MetricName") == spec["MetricName"]
        assert props.get("Threshold") == spec["Threshold"]
        assert props.get("Statistic") == spec["Statistic"]
        assert props.get("ComparisonOperator") == "GreaterThanOrEqualToThreshold"
        assert props.get("TreatMissingData") == "notBreaching"

        # Verify Dimensions
        dims = props.get("Dimensions", [])
        assert len(dims) >= 1
        dim = dims[0]
        assert dim.get("Name") == spec["DimensionName"]
        assert dim.get("Value") == spec["DimensionValue"]

        # Verify AlarmActions wired to SNS
        assert props.get("AlarmActions") == [{"Ref": "OperationalAlertsTopic"}]


# =========================================================================
# P1.19: Persistence, Recovery & Data Safety
# =========================================================================

def test_semantic_dynamodb_persistence_and_recovery(template):
    """P1.19: MainTable has continuous PITR, deletion protection, SSE encryption, and retain policies."""
    resources = template.get("Resources", {})
    assert "MainTable" in resources
    table = resources["MainTable"]

    assert table.get("Type") == "AWS::DynamoDB::Table"
    assert table.get("DeletionPolicy") == "Retain"
    assert table.get("UpdateReplacePolicy") == "Retain"

    props = table.get("Properties", {})
    assert props.get("BillingMode") == "PAY_PER_REQUEST"
    assert props.get("DeletionProtectionEnabled") is True
    assert props.get("PointInTimeRecoverySpecification", {}).get("PointInTimeRecoveryEnabled") is True
    assert props.get("SSESpecification", {}).get("SSEEnabled") is True
    assert props.get("TimeToLiveSpecification", {}).get("AttributeName") == "ttl"
    assert props.get("TimeToLiveSpecification", {}).get("Enabled") is True


def test_semantic_s3_frontend_bucket_hardening(template):
    """P1.19: FrontendBucket has object versioning, 30-day noncurrent expiration lifecycle, and retain policies."""
    resources = template.get("Resources", {})
    assert "FrontendBucket" in resources
    bucket = resources["FrontendBucket"]

    assert bucket.get("Type") == "AWS::S3::Bucket"
    assert bucket.get("DeletionPolicy") == "Retain"
    assert bucket.get("UpdateReplacePolicy") == "Retain"

    props = bucket.get("Properties", {})
    assert props.get("VersioningConfiguration", {}).get("Status") == "Enabled"

    rules = props.get("LifecycleConfiguration", {}).get("Rules", [])
    assert len(rules) >= 1
    rule = rules[0]
    assert rule.get("Status") == "Enabled"
    assert rule.get("NoncurrentVersionExpiration", {}).get("NoncurrentDays") == 30

    pab = props.get("PublicAccessBlockConfiguration", {})
    assert pab.get("BlockPublicAcls") is True
    assert pab.get("BlockPublicPolicy") is True
    assert pab.get("IgnorePublicAcls") is True
    assert pab.get("RestrictPublicBuckets") is True

    ownership = props.get("OwnershipControls", {}).get("Rules", [])
    assert len(ownership) >= 1
    assert ownership[0].get("ObjectOwnership") == "BucketOwnerEnforced"


# =========================================================================
# P1.20: Cost Controls & Denial-of-Wallet Resilience
# =========================================================================

def test_semantic_lambda_concurrency_ceilings(template):
    """P1.20: Every Lambda function has a protective ReservedConcurrentExecutions ceiling (total 190)."""
    resources = template.get("Resources", {})

    expected_concurrency = {
        "HealthFunction": 10,
        "GetLocationsFunction": 50,
        "GetQueueFunction": 50,
        "SubmitReportFunction": 20,
        "GetRecommendationsFunction": 30,
        "GetHistoricalFunction": 20,
        "AdminReportsFunction": 10,
    }

    total_concurrency = 0
    for func_name, expected_limit in expected_concurrency.items():
        assert func_name in resources
        func = resources[func_name]
        props = func.get("Properties", {})
        limit = props.get("ReservedConcurrentExecutions")
        assert limit == expected_limit, f"{func_name} has invalid ReservedConcurrentExecutions: {limit}"
        total_concurrency += limit

    assert total_concurrency == 190, f"Expected total concurrency 190, got {total_concurrency}"


def test_semantic_api_gateway_throttling_settings(template):
    """P1.20: API Gateway has default throttling and route-specific throttling for report submission."""
    resources = template.get("Resources", {})
    http_api = resources.get("QueueSenseHttpApi", {})
    props = http_api.get("Properties", {})

    default_throttle = props.get("DefaultRouteSettings", {})
    assert default_throttle.get("ThrottlingBurstLimit") == 100
    assert default_throttle.get("ThrottlingRateLimit") == 50.0

    route_throttle = props.get("RouteSettings", {}).get("POST /locations/{id}/reports", {})
    assert route_throttle.get("ThrottlingBurstLimit") == 20
    assert route_throttle.get("ThrottlingRateLimit") == 10.0


# =========================================================================
# IAM & Secrets Least-Privilege Verification
# =========================================================================

def test_semantic_submit_report_kms_least_privilege(template):
    """IAM: SubmitReportFunction KMS decrypt statement is locked to caller account, SSM service, and parameter encryption context."""
    resources = template.get("Resources", {})
    func = resources.get("SubmitReportFunction", {})
    policies = func.get("Properties", {}).get("Policies", [])

    kms_statement = None
    for pol in policies:
        if "Statement" in pol:
            for stmt in pol["Statement"]:
                if stmt.get("Sid") == "SubmitReportKMSDecryptionAccess":
                    kms_statement = stmt
                    break

    assert kms_statement is not None, "SubmitReportKMSDecryptionAccess statement missing"
    assert kms_statement.get("Action") == ["kms:Decrypt"]

    cond = kms_statement.get("Condition", {}).get("StringEquals", {})
    assert cond.get("kms:CallerAccount") == {"Sub": "${AWS::AccountId}"}
    assert cond.get("kms:ViaService") == {"Sub": "ssm.${AWS::Region}.amazonaws.com"}
    assert cond.get("kms:EncryptionContext:aws:ssm:arn") == {
        "Sub": "arn:aws:ssm:${AWS::Region}:${AWS::AccountId}:parameter/queuesense/${Environment}/rate_limit_salt"
    }


def test_semantic_iam_no_wildcards_in_any_policy(template):
    """IAM: Verifies that no Lambda execution role grants wildcard actions or dangerous administrative permissions."""
    resources = template.get("Resources", {})

    forbidden_action_patterns = [
        r"^dynamodb:\*$",
        r"^ssm:\*$",
        r"^kms:\*$",
        r"^s3:\*$",
        r"^dynamodb:DeleteTable$",
        r"^dynamodb:DropTable$",
    ]

    for res_name, res_val in resources.items():
        if res_val.get("Type") == "AWS::Serverless::Function":
            policies = res_val.get("Properties", {}).get("Policies", [])
            for pol in policies:
                if isinstance(pol, dict) and "Statement" in pol:
                    for stmt in pol["Statement"]:
                        actions = stmt.get("Action", [])
                        if isinstance(actions, str):
                            actions = [actions]
                        for act in actions:
                            for pat in forbidden_action_patterns:
                                assert not re.match(pat, act, re.IGNORECASE), (
                                    f"Forbidden action '{act}' found in {res_name}"
                                )


# =========================================================================
# Cognito Administrative Security & CloudFront Delivery
# =========================================================================

def test_semantic_cognito_mfa_and_admin_security(template):
    """Cognito: Mandatory TOTP MFA ('ON'), admin-only user creation, and user existence error masking."""
    resources = template.get("Resources", {})
    user_pool = resources.get("QueueSenseUserPool", {})
    props = user_pool.get("Properties", {})

    # Explicit security decision: MFA is set to ON (mandatory for all admins)
    assert props.get("MfaConfiguration") == "ON", "Cognito User Pool must enforce mandatory MfaConfiguration: 'ON'"
    assert props.get("EnabledMfas") == ["SOFTWARE_TOKEN_MFA"]

    admin_config = props.get("AdminCreateUserConfig", {})
    assert admin_config.get("AllowAdminCreateUserOnly") is True

    pwd_policy = props.get("Policies", {}).get("PasswordPolicy", {})
    assert pwd_policy.get("MinimumLength") >= 12
    assert pwd_policy.get("RequireUppercase") is True
    assert pwd_policy.get("RequireLowercase") is True
    assert pwd_policy.get("RequireNumbers") is True
    assert pwd_policy.get("RequireSymbols") is True

    # User Pool Client
    client = resources.get("QueueSenseUserPoolClient", {})
    client_props = client.get("Properties", {})
    assert client_props.get("PreventUserExistenceErrors") == "ENABLED"
    assert client_props.get("GenerateSecret") is False


def test_semantic_cloudfront_spa_routing_and_missing_assets(template):
    """CloudFront: SPA routing rewrites extensionless routes to /index.html via CloudFront Function; no global 403/404 rewrites."""
    resources = template.get("Resources", {})

    # 1. CloudFront Function exists
    assert "SpaRoutingFunction" in resources
    spa_fn = resources["SpaRoutingFunction"]
    assert spa_fn.get("Type") == "AWS::CloudFront::Function"
    fn_props = spa_fn.get("Properties", {})
    assert fn_props.get("AutoPublish") is True
    assert fn_props.get("FunctionConfig", {}).get("Runtime") == "cloudfront-js-2.0"

    fn_code = fn_props.get("FunctionCode", "")
    assert "!uri.includes('.')" in fn_code, "SPA function must check whether URI lacks file extension"
    assert "request.uri = '/index.html'" in fn_code

    # 2. Distribution references SpaRoutingFunction in viewer-request
    dist = resources.get("FrontendDistribution", {})
    dist_config = dist.get("Properties", {}).get("DistributionConfig", {})
    cache_behavior = dist_config.get("DefaultCacheBehavior", {})

    associations = cache_behavior.get("FunctionAssociations", [])
    assert len(associations) >= 1
    assert associations[0].get("EventType") == "viewer-request"
    assert associations[0].get("FunctionARN") == {"GetAtt": "SpaRoutingFunction.FunctionARN"}

    # 3. Global 403/404 rewrite MUST NOT exist (missing assets must return genuine 404, not index.html)
    assert "CustomErrorResponses" not in dist_config, (
        "Global CustomErrorResponses must be removed to avoid turning missing JS/CSS/image 404s into 200 index.html"
    )


def test_semantic_cloudfront_csp_and_security_headers(template):
    """CloudFront: Security headers policy has strict HSTS, nosniff, DENY frame options, and scoped CSP with zero wildcard *.amazonaws.com."""
    resources = template.get("Resources", {})
    policy = resources.get("FrontendResponseHeadersPolicy", {})
    sec_config = policy.get("Properties", {}).get("ResponseHeadersPolicyConfig", {}).get("SecurityHeadersConfig", {})

    # HSTS
    hsts = sec_config.get("StrictTransportSecurity", {})
    assert hsts.get("AccessControlMaxAgeSec") == 63072000
    assert hsts.get("IncludeSubdomains") is True
    assert hsts.get("Preload") is True

    # FrameOptions & ContentType
    assert sec_config.get("FrameOptions", {}).get("FrameOption") == "DENY"
    assert sec_config.get("ContentTypeOptions", {}).get("Override") is True

    # Content Security Policy
    csp_obj = sec_config.get("ContentSecurityPolicy", {}).get("ContentSecurityPolicy", {})
    csp_str = csp_obj.get("Sub", "") if isinstance(csp_obj, dict) else str(csp_obj)

    assert "default-src 'self'" in csp_str
    assert "script-src 'self'" in csp_str
    assert "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com" in csp_str
    assert "media-src 'self' blob:" in csp_str
    assert "object-src 'none'" in csp_str
    assert "frame-ancestors 'none'" in csp_str
    assert "base-uri 'self'" in csp_str

    # Must NOT have broad wildcard *.amazonaws.com
    assert "https://*.amazonaws.com" not in csp_str, (
        "CSP connect-src must not contain broad wildcard https://*.amazonaws.com"
    )
    assert "https://*.execute-api.${AWS::Region}.amazonaws.com" in csp_str
    assert "https://cognito-idp.${AWS::Region}.amazonaws.com" in csp_str


# =========================================================================
# Negative Tests: Catch Misconfigurations and Policy Violations
# =========================================================================

def test_negative_missing_retention_detected():
    """Negative Test: Verifies that a LogGroup without RetentionInDays fails validation."""
    malformed_log_group = {
        "Type": "AWS::Logs::LogGroup",
        "Properties": {
            "LogGroupName": "/aws/lambda/test"
            # Missing RetentionInDays
        }
    }
    with pytest.raises(AssertionError):
        assert malformed_log_group.get("Properties", {}).get("RetentionInDays") == 30


def test_negative_raw_ip_in_access_log_detected():
    """Negative Test: Verifies that an access log format containing sourceIp fails privacy validation."""
    malformed_format = json.dumps({"requestId": "$context.requestId", "ip": "$context.identity.sourceIp"})
    with pytest.raises(AssertionError):
        assert "ip" not in json.loads(malformed_format)
        assert "$context.identity.sourceIp" not in malformed_format


def test_negative_wildcard_iam_action_detected():
    """Negative Test: Verifies that a wildcard IAM action fails least-privilege validation."""
    malformed_statement = {"Action": ["dynamodb:*"], "Effect": "Allow", "Resource": "*"}
    with pytest.raises(AssertionError):
        for act in malformed_statement["Action"]:
            assert not re.match(r"^dynamodb:\*$", act)


def test_negative_optional_mfa_fails_enforcement_check():
    """Negative Test: Verifies that MfaConfiguration: OPTIONAL fails mandatory MFA assertion."""
    optional_mfa_props = {"MfaConfiguration": "OPTIONAL", "EnabledMfas": ["SOFTWARE_TOKEN_MFA"]}
    with pytest.raises(AssertionError):
        assert optional_mfa_props.get("MfaConfiguration") == "ON"
