from sportland_matcher.config import load_config, validate_config


def main():
    cfg = load_config()
    errors = validate_config(cfg)
    if errors:
        print("Configuration is NOT ready:")
        for error in errors:
            print(f" - {error}")
        raise SystemExit(2)
    print("Configuration OK.")
    print(f"Smart source: {cfg.smart_source}")
    print(f"Smart sheet: {cfg.smart_sheet_name}")
    print(f"Shopify host: {cfg.shopify_shop}")
    print(f"Shopify auth mode: {cfg.shopify_auth_mode}")
    print("Read-only V1.1 is ready to run.")


if __name__ == "__main__":
    main()
