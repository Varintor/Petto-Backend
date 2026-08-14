"""align wardrobe reward ids with the client catalogue

Revision ID: 0013_wardrobe_reward_ids
Revises: 0012_legacy_storage_owners
Create Date: 2026-08-14
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0013_wardrobe_reward_ids"
down_revision: Union[str, Sequence[str], None] = "0012_legacy_storage_owners"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Every pet starts with the same free collar. The unique constraint makes
    # this safe for databases where some pets already received it.
    op.execute(
        """
        INSERT INTO pet_wardrobe_items (pet_id, accessory_id)
        SELECT id, 'acc_collar' FROM pet_profiles
        ON CONFLICT (pet_id, accessory_id) DO NOTHING
        """
    )

    # Consolidate any number of legacy mission rows into one stable catalogue
    # item per pet. Repeated daily missions can award the same cosmetic, so an
    # in-place UPDATE would violate uq_pet_wardrobe_item.
    op.execute(
        """
        INSERT INTO pet_wardrobe_items (pet_id, accessory_id, unlocked_at)
        SELECT item.pet_id,
          CASE mission.mission_type
            WHEN 'walk' THEN 'acc_hat'
            WHEN 'water' THEN 'acc_water_bowl'
            WHEN 'ai_check' THEN 'acc_doctor_coat'
            WHEN 'grooming' THEN 'acc_brush'
            WHEN 'play' THEN 'acc_ball'
            WHEN 'photo' THEN 'acc_camera'
            WHEN 'dental_check' THEN 'acc_toothbrush'
            WHEN 'nail_check' THEN 'acc_nail_file'
            WHEN 'ear_check' THEN 'acc_ear_tag'
            WHEN 'weight_log' THEN 'acc_scale'
            WHEN 'bonding' THEN 'acc_heart'
            WHEN 'training' THEN 'acc_diploma'
            WHEN 'feeding_check' THEN 'acc_bowl'
            WHEN 'eye_nose_check' THEN 'acc_glasses'
            WHEN 'social' THEN 'acc_friendship'
          END AS stable_accessory_id,
          min(item.unlocked_at)
        FROM pet_wardrobe_items AS item
        JOIN daily_missions AS mission
          ON item.accessory_id = ('mission-' || mission.id::text)
        WHERE mission.mission_type IN (
          'walk', 'water', 'ai_check', 'grooming', 'play', 'photo',
          'dental_check', 'nail_check', 'ear_check', 'weight_log',
          'bonding', 'training', 'feeding_check', 'eye_nose_check', 'social'
        )
        GROUP BY item.pet_id, stable_accessory_id
        ON CONFLICT (pet_id, accessory_id) DO NOTHING
        """
    )
    op.execute(
        """
        DELETE FROM pet_wardrobe_items AS item
        USING daily_missions AS mission
        WHERE item.accessory_id = ('mission-' || mission.id::text)
          AND mission.mission_type IN (
            'walk', 'water', 'ai_check', 'grooming', 'play', 'photo',
            'dental_check', 'nail_check', 'ear_check', 'weight_log',
            'bonding', 'training', 'feeding_check', 'eye_nose_check', 'social'
          )
        """
    )


def downgrade() -> None:
    # Stable catalogue IDs and starter unlocks are valid user progress and are
    # intentionally preserved during an application rollback.
    pass
