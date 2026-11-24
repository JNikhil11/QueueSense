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

Includes:
- Reusable semantic validation functions applied across production fixtures.
- Positive semantic tests for all architecture components.
- Control test demonstrating unmodified production template passes all validators.
- Real mutation-based negative tests operating on deep copies of the parsed template.
"""

import os
import json
import re
import copy
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
# Reusable Semantic Validation Functions
# =========================================================================

def validate_log_groups_and_retention(tmpl: dict):
    """Validates that every Lambda function has a dedicated AWS::Logs::LogGroup with finite 30-day retention."""
    resources = tmpl.get("Resources", {})

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


def validate_api_gateway_access_logging_privacy(tmpl: dict):
    """Validates that API Gateway access logging uses structured JSON with safe operational fields, strictly excluding raw IP."""
    resources = tmpl.get("Resources", {})

    # Check dedicated log group
    assert "ApiAccessLogGroup" in resources, "ApiAccessLogGroup missing from template"
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


def validate_cloudwatch_alarms_and_sns_actions(tmpl: dict):
    """Validates CloudWatch alarms are configured with valid metric dimensions, thresholds, and wired to OperationalAlertsTopic."""
    resources = tmpl.get("Resources", {})

    # Verify SNS Topic and optional Subscription
    assert "OperationalAlertsTopic" in resources, "OperationalAlertsTopic missing from template"
    assert resources["OperationalAlertsTopic"]["Type"] == "AWS::SNS::Topic"
    assert "OperationalAlertsSubscription" in resources, "OperationalAlertsSubscription missing from template"
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
        assert props.get("AlarmActions") == [{"Ref": "OperationalAlertsTopic"}], (
            f"Alarm {alarm_id} must have AlarmActions wired to OperationalAlertsTopic"
        )


def validate_dynamodb_persistence_and_recovery(tmpl: dict):
    """Validates MainTable has continuous PITR, deletion protection, SSE encryption, and retain policies."""
    resources = tmpl.get("Resources", {})
    assert "MainTable" in resources, "MainTable missing from template"
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


def validate_s3_frontend_bucket_hardening(tmpl: dict):
    """Validates FrontendBucket has object versioning, 30-day noncurrent expiration lifecycle, and retain policies."""
    resources = tmpl.get("Resources", {})
    assert "FrontendBucket" in resources, "FrontendBucket missing from template"
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


def validate_lambda_concurrency_ceilings(tmpl: dict):
    """Validates that every Lambda function has a protective ReservedConcurrentExecutions ceiling (total 190)."""
    resources = tmpl.get("Resources", {})

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
        assert func_name in resources, f"Function {func_name} missing from template"
        func = resources[func_name]
        props = func.get("Properties", {})
        limit = props.get("ReservedConcurrentExecutions")
        assert limit == expected_limit, f"{func_name} has invalid ReservedConcurrentExecutions: {limit}"
        total_concurrency += limit

    assert total_concurrency == 190, f"Expected total concurrency 190, got {total_concurrency}"


def validate_api_gateway_throttling_settings(tmpl: dict):
    """Validates API Gateway has default route throttling and route-specific throttling for report submission."""
    resources = tmpl.get("Resources", {})
    http_api = resources.get("QueueSenseHttpApi", {})
    props = http_api.get("Properties", {})

    default_throttle = props.get("DefaultRouteSettings", {})
    assert default_throttle.get("ThrottlingBurstLimit") == 100
    assert default_throttle.get("ThrottlingRateLimit") == 50.0

    route_throttle = props.get("RouteSettings", {}).get("POST /locations/{id}/reports", {})
    assert route_throttle.get("ThrottlingBurstLimit") == 20
    assert route_throttle.get("ThrottlingRateLimit") == 10.0


def validate_submit_report_kms_least_privilege(tmpl: dict):
    """Validates SubmitReportFunction KMS decrypt statement is locked to caller account, SSM service, and parameter encryption context."""
    resources = tmpl.get("Resources", {})
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


def validate_iam_no_wildcards_in_any_policy(tmpl: dict):
    """Validates that no Lambda execution role grants wildcard actions or dangerous administrative permissions."""
    resources = tmpl.get("Resources", {})

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


def validate_cognito_mfa_and_admin_security(tmpl: dict):
    """Validates mandatory TOTP MFA ('ON'), admin-only user creation, and user existence error masking."""
    resources = tmpl.get("Resources", {})
    user_pool = resources.get("QueueSenseUserPool", {})
    props = user_pool.get("Properties", {})

    # Explicit security decision: MFA is set to ON (mandatory for all admins)
    assert props.get("MfaConfiguration") == "ON", (
        f"Cognito User Pool must enforce mandatory MfaConfiguration: 'ON', got {props.get('MfaConfiguration')}"
    )
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


def validate_cloudfront_spa_routing_and_missing_assets(tmpl: dict):
    """Validates CloudFront SPA routing rewrites extensionless routes to /index.html via CloudFront Function; no global 403/404 rewrites."""
    resources = tmpl.get("Resources", {})

    # 1. CloudFront Function exists
    assert "SpaRoutingFunction" in resources, "SpaRoutingFunction missing from template"
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


def validate_cloudfront_csp_and_security_headers(tmpl: dict):
    """Validates security headers policy has strict HSTS, nosniff, DENY frame options, and scoped CSP with zero wildcard *.amazonaws.com."""
    resources = tmpl.get("Resources", {})
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
# Positive Semantic Tests
# =========================================================================

def test_semantic_log_groups_and_retention(template):
    """P1.18: Every Lambda function has a dedicated AWS::Logs::LogGroup with finite 30-day retention."""
    validate_log_groups_and_retention(template)


def test_semantic_api_gateway_access_logging_privacy(template):
    """P1.18: API Gateway access logging uses structured JSON with safe operational fields, strictly excluding raw IP."""
    validate_api_gateway_access_logging_privacy(template)


def test_semantic_cloudwatch_alarms_and_sns_actions(template):
    """P1.18: CloudWatch alarms are configured with valid metric dimensions, thresholds, and wired to OperationalAlertsTopic."""
    validate_cloudwatch_alarms_and_sns_actions(template)


def test_semantic_dynamodb_persistence_and_recovery(template):
    """P1.19: MainTable has continuous PITR, deletion protection, SSE encryption, and retain policies."""
    validate_dynamodb_persistence_and_recovery(template)


def test_semantic_s3_frontend_bucket_hardening(template):
    """P1.19: FrontendBucket has object versioning, 30-day noncurrent expiration lifecycle, and retain policies."""
    validate_s3_frontend_bucket_hardening(template)


def test_semantic_lambda_concurrency_ceilings(template):
    """P1.20: Every Lambda function has a protective ReservedConcurrentExecutions ceiling (total 190)."""
    validate_lambda_concurrency_ceilings(template)


def test_semantic_api_gateway_throttling_settings(template):
    """P1.20: API Gateway has default throttling and route-specific throttling for report submission."""
    validate_api_gateway_throttling_settings(template)


def test_semantic_submit_report_kms_least_privilege(template):
    """IAM: SubmitReportFunction KMS decrypt statement is locked to caller account, SSM service, and parameter encryption context."""
    validate_submit_report_kms_least_privilege(template)


def test_semantic_iam_no_wildcards_in_any_policy(template):
    """IAM: Verifies that no Lambda execution role grants wildcard actions or dangerous administrative permissions."""
    validate_iam_no_wildcards_in_any_policy(template)


def test_semantic_cognito_mfa_and_admin_security(template):
    """Cognito: Mandatory TOTP MFA ('ON'), admin-only user creation, and user existence error masking."""
    validate_cognito_mfa_and_admin_security(template)


def test_semantic_cloudfront_spa_routing_and_missing_assets(template):
    """CloudFront: SPA routing rewrites extensionless routes to /index.html via CloudFront Function; no global 403/404 rewrites."""
    validate_cloudfront_spa_routing_and_missing_assets(template)


def test_semantic_cloudfront_csp_and_security_headers(template):
    """CloudFront: Security headers policy has strict HSTS, nosniff, DENY frame options, and scoped CSP with zero wildcard *.amazonaws.com."""
    validate_cloudfront_csp_and_security_headers(template)


# =========================================================================
# Control Test: Unmodified Production Template Verification
# =========================================================================

def test_control_unmodified_template_passes_all_validators(template):
    """Control Test: Proves that the pristine production template passes all 12 semantic validator functions."""
    validators = [
        validate_log_groups_and_retention,
        validate_api_gateway_access_logging_privacy,
        validate_cloudwatch_alarms_and_sns_actions,
        validate_dynamodb_persistence_and_recovery,
        validate_s3_frontend_bucket_hardening,
        validate_lambda_concurrency_ceilings,
        validate_api_gateway_throttling_settings,
        validate_submit_report_kms_least_privilege,
        validate_iam_no_wildcards_in_any_policy,
        validate_cognito_mfa_and_admin_security,
        validate_cloudfront_spa_routing_and_missing_assets,
        validate_cloudfront_csp_and_security_headers,
    ]
    for validator in validators:
        validator(template)


# =========================================================================
# Mutation-Based Negative Tests (Deep Copies of Production Template)
# =========================================================================

def test_negative_mutation_missing_log_retention_rejected(template):
    """Negative Mutation Test: Removing RetentionInDays from a LogGroup in a deep copy causes validate_log_groups_and_retention to fail."""
    mutated = copy.deepcopy(template)
    del mutated["Resources"]["HealthFunctionLogGroup"]["Properties"]["RetentionInDays"]
    with pytest.raises(AssertionError, match=r"HealthFunctionLogGroup must enforce RetentionInDays: 30"):
        validate_log_groups_and_retention(mutated)


def test_negative_mutation_raw_ip_in_access_log_rejected(template):
    """Negative Mutation Test: Injecting raw source IP into API Gateway access log format in a deep copy causes validate_api_gateway_access_logging_privacy to fail."""
    mutated = copy.deepcopy(template)
    log_format = json.loads(mutated["Resources"]["QueueSenseHttpApi"]["Properties"]["AccessLogSettings"]["Format"])
    log_format["ip"] = "$context.identity.sourceIp"
    mutated["Resources"]["QueueSenseHttpApi"]["Properties"]["AccessLogSettings"]["Format"] = json.dumps(log_format)
    with pytest.raises(AssertionError, match=r"Access log must NOT include raw IP address key"):
        validate_api_gateway_access_logging_privacy(mutated)


def test_negative_mutation_wildcard_iam_policy_rejected(template):
    """Negative Mutation Test: Adding a wildcard action (dynamodb:*) to a Lambda policy in a deep copy causes validate_iam_no_wildcards_in_any_policy to fail."""
    mutated = copy.deepcopy(template)
    mutated["Resources"]["SubmitReportFunction"]["Properties"]["Policies"][0]["Statement"].append({
        "Effect": "Allow",
        "Action": ["dynamodb:*"],
        "Resource": "*"
    })
    with pytest.raises(AssertionError, match=r"Forbidden action 'dynamodb:\*' found in SubmitReportFunction"):
        validate_iam_no_wildcards_in_any_policy(mutated)


def test_negative_mutation_optional_cognito_mfa_rejected(template):
    """Negative Mutation Test: Setting MfaConfiguration to OPTIONAL in a deep copy causes validate_cognito_mfa_and_admin_security to fail."""
    mutated = copy.deepcopy(template)
    mutated["Resources"]["QueueSenseUserPool"]["Properties"]["MfaConfiguration"] = "OPTIONAL"
    with pytest.raises(AssertionError, match=r"Cognito User Pool must enforce mandatory MfaConfiguration: 'ON'"):
        validate_cognito_mfa_and_admin_security(mutated)


def test_negative_mutation_missing_alarm_actions_rejected(template):
    """Negative Mutation Test: Removing AlarmActions from an alarm in a deep copy causes validate_cloudwatch_alarms_and_sns_actions to fail."""
    mutated = copy.deepcopy(template)
    mutated["Resources"]["Api5xxAlarm"]["Properties"]["AlarmActions"] = []
    with pytest.raises(AssertionError, match=r"Alarm Api5xxAlarm must have AlarmActions wired to OperationalAlertsTopic"):
        validate_cloudwatch_alarms_and_sns_actions(mutated)


def test_negative_mutation_missing_concurrency_rejected(template):
    """Negative Mutation Test: Removing ReservedConcurrentExecutions from a Lambda in a deep copy causes validate_lambda_concurrency_ceilings to fail."""
    mutated = copy.deepcopy(template)
    del mutated["Resources"]["SubmitReportFunction"]["Properties"]["ReservedConcurrentExecutions"]
    with pytest.raises(AssertionError, match=r"SubmitReportFunction has invalid ReservedConcurrentExecutions"):
        validate_lambda_concurrency_ceilings(mutated)
