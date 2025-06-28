import logging


def create_logger_from_designated_logger(logger_name: str, codebase_logger_level: int=logging.INFO):
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    logger = logging.getLogger("codebase_logger")
    logger.setLevel(codebase_logger_level)
    return logger.getChild(logger_name)


