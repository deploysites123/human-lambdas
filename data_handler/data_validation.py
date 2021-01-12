from ast import literal_eval

from schema import SchemaError

from .data_schema import DATA_SCHEMA

"""
The goal of these functions is to validate incoming data from external sources
according to each block type.

Data validation is run in the task serializer,
CSV processing (which runs outside of the serializer)
and the workflow serializer.

data_validation is the entry point.
It validates according to the internal definition of each block's value.
We use the internal and not external definition because validation is applied
after we have transformed from our external to internal representations.
"""


class DataValidationError(Exception):
    """Data validation error"""

    pass


def convert_string(input_value):
    try:
        return literal_eval(input_value)
    except (ValueError, SyntaxError):
        raise DataValidationError(
            f"The value provided is not in right format: {input_value}"
        )


def default_data_validation(data, is_workflow):
    pass


def validate_selection(data, is_workflow):
    type_data = data.get(data["type"])
    if type_data is None:
        raise DataValidationError("Type do not match to {}".format(data["type"]))
    if "options" not in type_data:
        raise DataValidationError("Selection blocks should have a list of options")


def validate_single_selection(data, is_workflow):
    validate_selection(data, is_workflow)


def validate_multiple_selection(data, is_workflow):
    validate_selection(data, is_workflow)


def validate_form(data, is_workflow):
    pass


def validate_list(data, is_workflow):
    list_value = data[data["type"]].get("value")
    if isinstance(list_value, str):
        list_value = convert_string(list_value)
    if list_value and not isinstance(list_value, list):
        raise DataValidationError(
            f"Data item with id {data['id']} is of type list thus should be a list"
        )
    data[data["type"]]["value"] = list_value


def validate_number(data, is_workflow):
    number_value = data[data["type"]].get("value")
    if isinstance(number_value, str):
        number_value = convert_string(number_value)
    if number_value and type(number_value) not in [int, float]:
        raise DataValidationError(
            f"Data item with id {data['id']} is of type number thus should be a float or a integer"
        )
    data[data["type"]]["value"] = number_value


def validate_named_entity_recognition(data, is_workflow):
    # Require a value key with string value when it's a task
    if (
        not is_workflow
        and "value" in data[data["type"]]
        and not isinstance(data[data["type"]].get("value"), (str, type(None)))
    ):
        raise DataValidationError(
            # Externally 'value' is set on 'text' key
            f"Data item with id {data['id']} is missing 'text' or is not a string."
        )
    # Require an entities key with list type
    if "entities" in data[data["type"]] and not isinstance(
        data[data["type"]]["entities"], list
    ):
        raise DataValidationError(
            f"Data item with id {data['id']} is missing 'entities' or not a list."
        )
    # Require an options key with list type
    if "options" in data[data["type"]] and not isinstance(
        data[data["type"]].get("options"), list
    ):
        raise DataValidationError(
            f"Data item with id {data['id']} is missing 'options' or not a list."
        )

        # Enforce objects key with list type
        if not isinstance(data[data["type"]].get("entities"), (list, type(None))):
            raise DataValidationError(
                f"Data item with id {data['id']} doesn't have a valid 'entities' value."
            )

    # Enforce entity schema for any entity
    for entity in data[data["type"]].get("entities", []):
        if (
            not isinstance(entity.get("start"), int)
            or not isinstance(entity.get("end"), int)
            or not isinstance(entity.get("tag"), str)
        ):
            raise DataValidationError(
                f"Entity {entity} missing one or more properties."
            )


def validate_bounding_boxes(data, is_workflow):
    # Enforce options is list
    if not isinstance(data[data["type"]].get("options"), []):
        raise DataValidationError(
            f"Data item with id {data['id']} is missing 'options' or not a list."
        )

    # if it's a task
    if not is_workflow:
        # Enforce value of dict type
        if not isinstance(data[data["type"]].get("value"), dict):
            raise DataValidationError(
                f"Data item with id {data['id']} is not an object."
            )

        # Enforce image key with string type
        if not isinstance(data[data["type"]]["value"].get("image"), (str, type(None))):
            raise DataValidationError(
                f"Data item with id {data['id']} doesn't have a valid 'image' value."
            )

        # Enforce objects key with list type
        if not isinstance(
            data[data["type"]]["value"].get("objects"), (list, type(None))
        ):
            raise DataValidationError(
                f"Data item with id {data['id']} doesn't have a valid 'objects' value."
            )

        # Enforce objects schema if there is any
        for bounding_box in data[data["type"]]["value"].get("objects", []):
            if (
                not isinstance(bounding_box, dict)
                or not isinstance(bounding_box.get("x"), str)
                or not isinstance(bounding_box.get("y"), str)
                or not isinstance(bounding_box.get("w"), str)
                or not isinstance(bounding_box.get("h"), str)
                or not isinstance(bounding_box.get("category"), str)
            ):
                raise DataValidationError(
                    f"Data item with id {data['id']} doesn't have a valid object in 'objects'."
                )


VALIDATION_STATES = {
    "single_selection": validate_single_selection,
    "multiple_selection": validate_multiple_selection,
    "form_sequence": validate_form,
    "list": validate_list,
    "number": validate_number,
    "named_entity_recognition": validate_named_entity_recognition,
    "bounding_boxes": validate_bounding_boxes,
}


def data_validation(data, is_workflow=False):
    try:
        data = DATA_SCHEMA.validate(data)
    except SchemaError as exception_text:
        raise DataValidationError(exception_text)
    for data_item in data:
        VALIDATION_STATES.get(data_item["type"], default_data_validation)(
            data_item, is_workflow
        )
    return data
