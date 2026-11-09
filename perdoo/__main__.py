from perdoo.cli._parser import build_parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    result = args.func(args)
    if getattr(result, "failed", 0):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
