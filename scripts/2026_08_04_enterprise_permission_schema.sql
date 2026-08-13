-- 企业级权限与资源隔离系统建表脚本
-- 范围：组织用户、角色权限、动态协作与临时授权。
-- 不包含知识库相关表：kb_space、kb_document、kb_space_acl、kb_doc_acl。

SET NAMES utf8mb4;
SET UNIQUE_CHECKS = 0;
SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE IF NOT EXISTS `iam_users` (
  `id` BIGINT NOT NULL COMMENT '主键ID',
  `username` VARCHAR(64) NOT NULL COMMENT '登录账号',
  `display_name` VARCHAR(128) DEFAULT NULL COMMENT '显示名称',
  `is_platform_admin` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否平台管理员：1-是，0-否',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用：1-启用，0-停用',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_iam_users_username` (`username`),
  KEY `idx_iam_users_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IAM 平台用户表';

CREATE TABLE IF NOT EXISTS `iam_user_credentials` (
  `user_id` BIGINT NOT NULL COMMENT '用户ID，与 iam_users.id 一一对应',
  `password_hash` VARCHAR(255) NOT NULL COMMENT '密码哈希，格式 pbkdf2_sha256$<iter>$<salt_hex>$<hash_hex>',
  `token_version` INT NOT NULL DEFAULT 0 COMMENT '凭证版本号，自增；登出/重置密码时 +1 使历史 token 失效',
  `failed_attempts` INT NOT NULL DEFAULT 0 COMMENT '连续登录失败次数，成功后清零',
  `locked_until` DATETIME DEFAULT NULL COMMENT '锁定截止时间，NULL 表示未锁定',
  `last_login_at` DATETIME DEFAULT NULL COMMENT '最近一次登录成功时间',
  `password_changed_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '最近一次修改密码时间',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`user_id`),
  CONSTRAINT `fk_iam_user_credentials_user_id` FOREIGN KEY (`user_id`) REFERENCES `iam_users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IAM 用户凭证表（密码哈希与登录状态）';

CREATE TABLE IF NOT EXISTS `iam_tenants` (
  `id` BIGINT NOT NULL COMMENT '主键ID',
  `code` VARCHAR(64) NOT NULL COMMENT '租户编码',
  `name` VARCHAR(128) NOT NULL COMMENT '租户名称',
  `status` VARCHAR(32) NOT NULL DEFAULT 'active' COMMENT '租户状态：active-启用',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_iam_tenants_code` (`code`),
  KEY `idx_iam_tenants_code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IAM 租户表';

CREATE TABLE IF NOT EXISTS `iam_tenant_members` (
  `id` BIGINT NOT NULL COMMENT '主键ID',
  `tenant_id` BIGINT NOT NULL COMMENT '租户ID',
  `user_id` BIGINT NOT NULL COMMENT '用户ID',
  `status` VARCHAR(32) NOT NULL DEFAULT 'active' COMMENT '成员状态：active-有效',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_iam_member_tenant_user` (`tenant_id`, `user_id`),
  KEY `idx_iam_tenant_members_tenant_id` (`tenant_id`),
  KEY `idx_iam_tenant_members_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IAM 租户成员表';

CREATE TABLE IF NOT EXISTS `iam_roles` (
  `id` BIGINT NOT NULL COMMENT '主键ID',
  `tenant_id` BIGINT NOT NULL COMMENT '租户ID',
  `code` VARCHAR(64) NOT NULL COMMENT '角色编码',
  `name` VARCHAR(128) NOT NULL COMMENT '角色名称',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_iam_role_tenant_code` (`tenant_id`, `code`),
  KEY `idx_iam_roles_tenant_id` (`tenant_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IAM 租户角色表';

CREATE TABLE IF NOT EXISTS `iam_permissions` (
  `id` BIGINT NOT NULL COMMENT '主键ID',
  `code` VARCHAR(128) NOT NULL COMMENT '权限编码',
  `name` VARCHAR(128) NOT NULL COMMENT '权限名称',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_iam_permissions_code` (`code`),
  KEY `idx_iam_permissions_code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IAM 权限定义表';

CREATE TABLE IF NOT EXISTS `iam_tenant_member_roles` (
  `id` BIGINT NOT NULL COMMENT '主键ID',
  `member_id` BIGINT NOT NULL COMMENT '租户成员ID',
  `role_id` BIGINT NOT NULL COMMENT '角色ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_iam_member_role` (`member_id`, `role_id`),
  KEY `idx_iam_tenant_member_roles_member_id` (`member_id`),
  KEY `idx_iam_tenant_member_roles_role_id` (`role_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IAM 成员角色关联表';

CREATE TABLE IF NOT EXISTS `iam_role_permissions` (
  `id` BIGINT NOT NULL COMMENT '主键ID',
  `role_id` BIGINT NOT NULL COMMENT '角色ID',
  `permission_id` BIGINT NOT NULL COMMENT '权限ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_iam_role_permission` (`role_id`, `permission_id`),
  KEY `idx_iam_role_permissions_role_id` (`role_id`),
  KEY `idx_iam_role_permissions_permission_id` (`permission_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='IAM 角色权限关联表';

CREATE TABLE IF NOT EXISTS `sys_dept` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `parent_id` BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '父部门ID',
  `dept_name` VARCHAR(100) NOT NULL COMMENT '部门名称',
  `dept_path` VARCHAR(500) NOT NULL COMMENT '部门层级路径，如 /1/10/105/',
  `dept_tags` JSON DEFAULT NULL COMMENT '部门标签，用于ABAC属性匹配，如 ["高管", "研发"]',
  `sort_order` INT NOT NULL DEFAULT 0 COMMENT '显示排序',
  `status` TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1-正常，0-停用',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_sys_dept_parent_id` (`parent_id`),
  KEY `idx_sys_dept_dept_path` (`dept_path`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='部门表';

CREATE TABLE IF NOT EXISTS `sys_user` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `username` VARCHAR(50) NOT NULL COMMENT '登录账号',
  `real_name` VARCHAR(50) NOT NULL COMMENT '真实姓名',
  `status` TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1-正常，0-锁定',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户基础信息表';

CREATE TABLE IF NOT EXISTS `sys_user_dept` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `user_id` BIGINT UNSIGNED NOT NULL COMMENT '用户ID',
  `dept_id` BIGINT UNSIGNED NOT NULL COMMENT '部门ID',
  `is_primary` TINYINT NOT NULL DEFAULT 0 COMMENT '是否主部门：1-是，0-否',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_dept` (`user_id`, `dept_id`),
  KEY `idx_sys_user_dept_user_primary` (`user_id`, `is_primary`),
  KEY `idx_sys_user_dept_dept_id` (`dept_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户-部门关联表';

CREATE TABLE IF NOT EXISTS `sys_role` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `role_name` VARCHAR(50) NOT NULL COMMENT '角色名称',
  `role_key` VARCHAR(50) NOT NULL COMMENT '角色标识',
  `data_scope` TINYINT NOT NULL DEFAULT 1 COMMENT '数据范围：1-全部，2-本部门及以下，3-仅本部门，4-仅本人，5-自定义部门，6-按标签',
  `data_scope_rule` JSON DEFAULT NULL COMMENT '数据范围扩展规则，如标签匹配条件或自定义部门ID列表',
  `status` TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1-正常，0-停用',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_sys_role_role_key` (`role_key`),
  KEY `idx_sys_role_data_scope` (`data_scope`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='角色表';

CREATE TABLE IF NOT EXISTS `sys_menu` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `parent_id` BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '父菜单ID',
  `menu_name` VARCHAR(50) NOT NULL COMMENT '菜单名称',
  `menu_type` CHAR(1) NOT NULL COMMENT '类型：M-目录，C-菜单，F-按钮/资源',
  `permission` VARCHAR(100) DEFAULT NULL COMMENT '权限标识，如 system:user:add',
  `path` VARCHAR(200) DEFAULT NULL COMMENT '路由地址',
  `sort_order` INT NOT NULL DEFAULT 0 COMMENT '显示排序',
  `status` TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1-正常，0-隐藏',
  PRIMARY KEY (`id`),
  KEY `idx_sys_menu_parent_id` (`parent_id`),
  KEY `idx_sys_menu_permission` (`permission`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='菜单/资源表';

CREATE TABLE IF NOT EXISTS `sys_role_menu` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `role_id` BIGINT UNSIGNED NOT NULL COMMENT '角色ID',
  `menu_id` BIGINT UNSIGNED NOT NULL COMMENT '菜单/资源ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_role_menu` (`role_id`, `menu_id`),
  KEY `idx_sys_role_menu_menu_id` (`menu_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='角色-菜单关联表';

CREATE TABLE IF NOT EXISTS `sys_user_role` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `user_id` BIGINT UNSIGNED NOT NULL COMMENT '用户ID',
  `role_id` BIGINT UNSIGNED NOT NULL COMMENT '角色ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_role` (`user_id`, `role_id`),
  KEY `idx_sys_user_role_role_id` (`role_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户-角色关联表';

CREATE TABLE IF NOT EXISTS `sys_role_dept` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `role_id` BIGINT UNSIGNED NOT NULL COMMENT '角色ID',
  `dept_id` BIGINT UNSIGNED NOT NULL COMMENT '部门ID',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_role_dept` (`role_id`, `dept_id`),
  KEY `idx_sys_role_dept_dept_id` (`dept_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='角色-部门关联表（自定义数据权限）';

CREATE TABLE IF NOT EXISTS `sys_temp_auth` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `user_id` BIGINT UNSIGNED NOT NULL COMMENT '被授权用户ID',
  `resource_type` VARCHAR(20) NOT NULL COMMENT '资源类型：MENU, DEPT, DOC',
  `resource_id` BIGINT UNSIGNED NOT NULL COMMENT '资源ID',
  `permission` VARCHAR(100) NOT NULL COMMENT '授予的权限标识',
  `start_time` DATETIME NOT NULL COMMENT '生效时间',
  `end_time` DATETIME NOT NULL COMMENT '过期时间',
  `grant_reason` VARCHAR(255) DEFAULT NULL COMMENT '授权原因',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_sys_temp_auth_user_resource_end` (`user_id`, `resource_id`, `end_time`),
  KEY `idx_sys_temp_auth_resource` (`resource_type`, `resource_id`, `permission`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='临时授权表';

CREATE TABLE IF NOT EXISTS `sys_workspace` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `space_name` VARCHAR(100) NOT NULL COMMENT '空间名称',
  `space_desc` VARCHAR(500) DEFAULT NULL COMMENT '空间描述',
  `owner_id` BIGINT UNSIGNED NOT NULL COMMENT '空间所有者用户ID',
  `status` TINYINT NOT NULL DEFAULT 1 COMMENT '状态：1-正常，0-归档',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_sys_workspace_owner_id` (`owner_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='业务空间表';

CREATE TABLE IF NOT EXISTS `sys_workspace_member` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `workspace_id` BIGINT UNSIGNED NOT NULL COMMENT '空间ID',
  `user_id` BIGINT UNSIGNED NOT NULL COMMENT '用户ID',
  `role` VARCHAR(20) NOT NULL COMMENT '空间内角色：OWNER, ADMIN, MEMBER, GUEST',
  `joined_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '加入时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_ws_member` (`workspace_id`, `user_id`),
  KEY `idx_sys_workspace_member_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='空间成员表';

SET FOREIGN_KEY_CHECKS = 1;
SET UNIQUE_CHECKS = 1;
